"""Read account quota through the installed Codex app-server (no model turns)."""
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import threading
import time

from PySide6.QtCore import QThread, Signal


class UsageError(Exception):
    pass


def quota_window(value):
    if value is None:
        return None
    used = value.get('usedPercent')
    minutes = value.get('windowDurationMins')
    reset = value.get('resetsAt')
    if not isinstance(used, (int, float)) or not math.isfinite(used):
        raise UsageError('Codex返回的额度百分比无效')
    if minutes is not None and (not isinstance(minutes, (int, float)) or not math.isfinite(minutes) or minutes <= 0):
        raise UsageError('Codex返回的额度周期无效')
    if reset is not None and (not isinstance(reset, (int, float)) or not math.isfinite(reset)):
        raise UsageError('Codex返回的重置时间无效')
    return dict(remaining=max(0, min(100, 100-used)), minutes=minutes, resets_at=reset)


def read_usage(stopped=None, command=None, timeout=15):
    stopped = stopped or threading.Event()
    command = command or shutil.which('codex')
    if not command:
        local = Path.home()/'.local/bin/codex'
        command = str(local) if os.access(local, os.X_OK) else None
    if not command:
        raise UsageError('未找到Codex CLI，请先安装并登录Codex')
    process = subprocess.Popen([command, 'app-server'], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    buffer = b''
    deadline = time.monotonic()+timeout

    def send(message):
        process.stdin.write((json.dumps(message)+'\n').encode())
        process.stdin.flush()

    def rpc(request_id, method, params):
        nonlocal buffer
        send(dict(id=request_id, method=method, params=params))
        while not stopped.is_set():
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                message = json.loads(line)
                if message.get('id') == request_id:
                    if 'error' in message:
                        # Never surface raw server errors: they can contain account details.
                        raise UsageError(f'Codex查询失败（{method}），请检查登录与网络')
                    return message['result']
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise UsageError('Codex额度查询超时，请检查网络；60秒后重试')
            if selector.select(min(.25, remaining)):
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    raise UsageError('Codex额度服务已退出；60秒后重试')
                buffer += chunk
        raise UsageError('查询已停止')

    try:
        rpc(0, 'initialize', {'clientInfo': {'name': 'pulse_monitor', 'version': '0.1.0'}})
        send({'method': 'initialized'})
        account = rpc(1, 'account/read', {'refreshToken': False}).get('account')
        if not account:
            raise UsageError('尚未登录Codex，请在Codex中使用ChatGPT账号登录')
        if account.get('type') != 'chatgpt':
            raise UsageError('当前为API或其他认证方式，ChatGPT订阅额度不可用')
        result = rpc(2, 'account/rateLimits/read', {})
        buckets = result.get('rateLimitsByLimitId')
        limits = buckets.get('codex') if buckets else result.get('rateLimits')
        if not limits:
            raise UsageError('服务未返回Codex订阅额度；60秒后重试')
        return dict(email=account.get('email') or 'ChatGPT账号',
                    plan=account.get('planType') or '',
                    windows=[quota_window(limits.get(key)) for key in ('primary', 'secondary')],
                    updated_at=time.time())
    finally:
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        process.stdin.close()
        process.stdout.close()


class UsagePoller(QThread):
    updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self.stopped = threading.Event()

    def run(self):
        while not self.stopped.is_set():
            try:
                result = read_usage(self.stopped)
            except UsageError as error:
                result = dict(error=str(error))
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                result = dict(error='Codex额度读取失败，请检查CLI版本与登录状态；60秒后重试')
            if not self.stopped.is_set():
                self.updated.emit(result)
            self.stopped.wait(60)

    def stop(self):
        self.stopped.set()
        self.wait()
