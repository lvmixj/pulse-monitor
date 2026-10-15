import argparse
import faulthandler
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .collector import Collector
from .theme import STYLE
from .ui import MainWindow
from .panel_config import read_panel


class Sampler(QThread):
    sampled = Signal(dict)
    failed = Signal(str)

    def __init__(self, interval=1):
        super().__init__()
        self.interval = interval
        self.stopped = threading.Event()

    def set_interval(self, value):
        self.interval = value

    def run(self):
        try:
            collector = Collector()
            # Both overall CPU and process CPU need a nonzero baseline interval.
            if self.stopped.wait(.3):
                return
            while not self.stopped.is_set():
                started = time.monotonic()
                self.sampled.emit(collector.sample())
                self.stopped.wait(max(.1, self.interval-(time.monotonic()-started)))
        except Exception as error:
            logging.exception('Resource sampling stopped')
            self.failed.emit(f'采集已停止：{type(error).__name__}: {error}。请重启Pulse。')

    def stop(self):
        self.stopped.set()
        self.wait()


def main():
    parser = argparse.ArgumentParser(description='Pulse本机资源监控')
    parser.add_argument('--widget', action='store_true', help='仅显示桌面小组件')
    parser.add_argument('--background', action='store_true', help='后台采集与顶栏')
    parser.add_argument('--client', action='store_true', help='只向已运行的后台发送命令')
    parser.add_argument('--toggle-widget', action='store_true')
    parser.add_argument('--quit', action='store_true')
    parser.add_argument('--page', choices=['overview', 'cpu', 'gpu', 'settings', 'panel'])
    args = parser.parse_args()
    faulthandler.enable()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    app = QApplication(sys.argv[:1])
    app.setApplicationName('pulse-monitor')
    app.setOrganizationName('Pulse')
    app.setDesktopFileName('pulse-monitor')
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    # Forward launches to the running application instead of duplicating samplers.
    name = f'pulse-resource-monitor-{os.getuid()}'
    client = QLocalSocket()
    client.connectToServer(name)
    connected = client.waitForConnected(500)
    if args.client:
        deadline = time.monotonic()+5
        while not connected and time.monotonic() < deadline:
            client.abort()
            client.connectToServer(name)
            connected = client.waitForConnected(200)
            if not connected:
                time.sleep(.1)
    if connected:
        command = ('quit' if args.quit else 'toggle-widget' if args.toggle_widget else
                   'widget' if args.widget else 'page:'+args.page if args.page else
                   'background' if args.background else 'main')
        client.write(command.encode())
        client.waitForBytesWritten(1000)
        client.disconnectFromServer()
        return 0
    if args.client or args.quit:
        logging.error('Pulse background is unavailable; start pulse-monitor.service')
        return 1
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(name):
        print(f'无法创建本机通信入口：{server.errorString()}', file=sys.stderr)
        return 1
    window = MainWindow()
    connections = []

    def accept():
        socket = server.nextPendingConnection()
        connections.append(socket)
        def handle():
            command = bytes(socket.readAll())
            if command == b'widget':
                window.toggle_widget(True)
            elif command == b'toggle-widget':
                window.toggle_widget(not window.widget.isVisible())
            elif command == b'quit':
                logging.info('Explicit quit requested')
                app.quit()
            elif command.startswith(b'page:'):
                page = command[5:].decode()
                if page in window.pages:
                    window.navigate(page)
                    window.show_main()
            elif command == b'background':
                pass
            else:
                window.show_main()
            socket.disconnectFromServer()
        socket.readyRead.connect(handle)
        socket.disconnected.connect(lambda: (connections.remove(socket), socket.deleteLater()))
        if socket.bytesAvailable():
            handle()
    server.newConnection.connect(accept)
    sampler = Sampler(window.settings.value('interval', 1, int))
    sampler.sampled.connect(window.receive)
    sampler.failed.connect(lambda message: (logging.error(message), app.exit(1)))
    window.interval_changed.connect(sampler.set_interval)
    app.aboutToQuit.connect(sampler.stop)
    app.aboutToQuit.connect(lambda: window.settings.setValue('widget_pos', window.widget.pos()))
    app.aboutToQuit.connect(lambda: window.settings.setValue('geometry', window.saveGeometry()))
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    snapshot_path = runtime/'pulse-monitor.json'
    latest = {}

    def publish(sample=None):
        if sample is not None:
            latest.clear()
            latest.update(dict(wall_time=sample['wall_time'], cpu=sample['cpu'], cores=sample['cores'], frequency=sample['frequency'],
                memory_used=sample['memory']['used'], memory_percent=sample['memory']['percent'], cpus=sample['cpus'],
                down=sample['network']['down'], up=sample['network']['up'],
                gpu=sample['gpus'][0] if sample['gpus'] else None, pid=os.getpid()))
        if not latest:
            return
        latest['widget_visible'] = window.widget.isVisible()
        latest['window_visible'] = window.isVisible()
        latest['page'] = window.current_page
        latest['panel'] = read_panel(window.settings)
        temporary = snapshot_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(latest))
        temporary.chmod(0o600)
        temporary.replace(snapshot_path)

    sampler.sampled.connect(publish)
    indicator = None
    def ensure_indicator():
        nonlocal indicator
        marker = runtime/'pulse-panel-native.json'
        native = marker.exists() and time.time()-marker.stat().st_mtime < 12
        if native:
            if indicator is not None and indicator.poll() is None:
                indicator.terminate()
                indicator.wait(timeout=3)
            indicator = None
            return
        if indicator is None or indicator.poll() is not None:
            if indicator is not None:
                logging.warning('Panel process exited with %s; restarting', indicator.returncode)
            indicator = subprocess.Popen(['/usr/bin/python3', '-m', 'pulse.indicator'], cwd=Path(__file__).resolve().parent.parent)

    def cleanup():
        logging.info('Pulse backend shutting down')
        if indicator is not None and indicator.poll() is None:
            indicator.terminate()
            try:
                indicator.wait(timeout=3)
            except subprocess.TimeoutExpired:
                indicator.kill()
                indicator.wait()
        snapshot_path.unlink(missing_ok=True)

    app.aboutToQuit.connect(cleanup)
    watchdog = QTimer()
    watchdog.timeout.connect(ensure_indicator)
    watchdog.start(5000)
    heartbeat = QTimer()
    heartbeat.timeout.connect(publish)
    heartbeat.start(1000)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda signum, frame: app.quit())
    ensure_indicator()
    if args.widget:
        window.toggle_widget(True)
    elif args.background:
        if window.settings.value('widget_visible', False, bool):
            window.toggle_widget(True)
    else:
        window.show()
        if window.settings.value('widget_visible', False, bool):
            window.toggle_widget(True)
    sampler.start()
    logging.info('Pulse backend ready, PID=%s, background=%s', os.getpid(), args.background)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
