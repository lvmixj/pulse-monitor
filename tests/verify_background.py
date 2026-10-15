"""Opt-in desktop integration test. Restarts only Pulse's own user service."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parents[1]
native_marker = Path(os.environ['XDG_RUNTIME_DIR'])/'pulse-panel-native.json'
if native_marker.exists() and time.time()-native_marker.stat().st_mtime < 12:
    import sys
    os.execv(str(ROOT/'.venv/bin/python'), [str(ROOT/'.venv/bin/python'), str(ROOT/'tests/verify_panel.py')])
STATE = Path(os.environ['XDG_RUNTIME_DIR'])/'pulse-monitor.json'
checks = []


def state():
    return json.loads(STATE.read_text())


def wait_for(predicate, timeout=12):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(.15)
    raise AssertionError('Timed out waiting for Pulse integration state')


def check(condition, name):
    assert condition, name
    checks.append(name)
    print('PASS', name, flush=True)


def run(*args):
    subprocess.run([str(ROOT/'run.sh'), *args], check=True, timeout=10)


def indicator_proxy():
    watcher = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION, 0, None,
        'org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher', 'org.kde.StatusNotifierWatcher', None)
    entries = watcher.get_cached_property('RegisteredStatusNotifierItems').unpack()
    item = next((i for i in entries if i.endswith('/org/ayatana/NotificationItem/pulse_monitor')), None)
    if not item:
        return None
    name, path = item.split('/', 1)
    proxy = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION, 0, None,
        name, '/'+path, 'org.kde.StatusNotifierItem', None)
    label = proxy.get_cached_property('XAyatanaLabel')
    return proxy if label is not None and 'CPU' in label.unpack() else None


subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'pulse-monitor.service'], check=True)
check(time.time()-state()['wall_time'] < 4, '托管后台持续发布新鲜采样')
wait_for(lambda: 'window_visible' in state())
proxy = wait_for(indicator_proxy)
label = proxy.get_cached_property('XAyatanaLabel').unpack()
check('CPU' in label and 'GPU' in label and '内存' in label and '↓' in label, '顶栏注册并显示真实资源指标')
connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
menu_path = proxy.get_cached_property('Menu').unpack()


def menu_nodes():
    response = connection.call_sync(proxy.get_name(), menu_path, 'com.canonical.dbusmenu',
        'GetLayout', GLib.Variant('(iias)', (0, -1, ['label'])), None, 0, 3000, None).unpack()
    nodes = []
    def walk(node):
        if isinstance(node, GLib.Variant):
            node = node.unpack()
        ident, props, children = node
        nodes.append((ident, props))
        for child in children:
            walk(child)
    walk(response[1])
    return nodes


def activate(text):
    ident = next(i for i, props in menu_nodes() if props.get('label') == text)
    connection.call_sync(proxy.get_name(), menu_path, 'com.canonical.dbusmenu', 'Event',
        GLib.Variant('(isvu)', (ident, 'clicked', GLib.Variant('s', ''), 0)), None, 0, 3000, None)


activate('查看CPU各核心')
wait_for(lambda: state()['window_visible'] and state()['page'] == 'cpu')
check(True, '顶栏菜单实际打开CPU核心页面')
activate('查看GPU利用率')
wait_for(lambda: state()['window_visible'] and state()['page'] == 'gpu')
check(True, '顶栏菜单实际打开GPU利用率页面')
initial_widget = state()['widget_visible']
activate('隐藏桌面小组件' if initial_widget else '显示桌面小组件')
wait_for(lambda: state()['widget_visible'] != initial_widget)
check(True, '顶栏菜单实际控制小组件显示状态')
if state()['widget_visible']:
    run('--toggle-widget')
    wait_for(lambda: not state()['widget_visible'])
run('--page', 'overview')
wait_for(lambda: state()['window_visible'] and state()['page'] == 'overview')
wid = subprocess.check_output(['xdotool', 'search', '--name', 'Pulse · 系统资源监控'], text=True).splitlines()[0]
subprocess.run(['xdotool', 'key', 'Escape'], check=True)
subprocess.run(['xdotool', 'windowactivate', '--sync', wid], check=True)
time.sleep(.3)
subprocess.run(['xdotool', 'key', 'alt+F4'], check=True)
wait_for(lambda: not state()['window_visible'])
before = state()['wall_time']
wait_for(lambda: state()['wall_time'] > before+1)
check(True, '主窗口和小组件均关闭时后台与顶栏继续采样')
old = state()['pid']
os.kill(old, signal.SIGKILL)
wait_for(lambda: state()['pid'] != old and time.time()-state()['wall_time'] < 3)
check(True, '强制异常终止后systemd自动恢复后台采样')
wait_for(indicator_proxy)
check(True, '后台恢复后顶栏自动重新注册')
proxy = indicator_proxy()
menu_path = proxy.get_cached_property('Menu').unpack()
activate('退出Pulse监控')
wait_for(lambda: not STATE.exists())
time.sleep(2.5)
status = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'pulse-monitor.service']).returncode
check(status != 0, '主动退出后保持停止，不被异常重启策略重新拉起')
run('--widget')
wait_for(lambda: state()['widget_visible'] and time.time()-state()['wall_time'] < 3)
check(True, '应用启动入口可重新启动托管后台并显示小组件')
wait_for(indicator_proxy)
check(True, '重新启动后顶栏恢复')
report = dict(checks=checks, count=len(checks), final_state=state())
(ROOT/'artifacts/background-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(f'{len(checks)} integration checks passed')
