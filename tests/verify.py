"""Actual-machine acceptance checks. Writes screenshots and a JSON report."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil
from PySide6.QtCore import QEventLoop, QPoint, QSettings, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pulse.collector import Collector, delta_rate
from pulse.theme import STYLE
from pulse.ui import MainWindow, gpu_usage
from pulse.__main__ import Sampler
from pulse.panel_config import read_panel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'artifacts'
OUT.mkdir(exist_ok=True)
checks = []


def check(condition, name):
    assert condition, name
    checks.append(name)
    print('PASS', name, flush=True)


app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
app.setQuitOnLastWindowClosed(False)
probe_timer = QTimer()
probe_timer.setInterval(1000)
baseline = sys.getrefcount(None)
for _ in range(1000):
    probe_timer.setInterval(1000)
reference_delta = sys.getrefcount(None)-baseline
check(reference_delta >= -10, 'Qt运行库连续调用不异常减少None引用')
with tempfile.TemporaryDirectory(prefix='pulse-verify-') as temp:
    settings = QSettings(str(Path(temp)/'settings.ini'), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    window.setWindowTitle('Pulse acceptance verification')
    window.show()
    QTest.qWait(100)
    collector = Collector()
    QTest.qWait(300)
    first = collector.sample()
    window.receive(first)
    check(0 <= first['cpu'] <= 100 and len(first['cpus']) == psutil.cpu_count(), '真实CPU与逻辑核心数据')
    check(abs(first['memory']['used']/first['memory']['total']*100-first['memory']['percent']) < .1, '内存百分比与容量采用同一口径')
    check(first['memory']['total'] == psutil.virtual_memory().total, '内存总量与操作系统一致')
    check(delta_rate(200, 100, 2) == 50 and delta_rate(10, 100, 2) == 0, '速率使用真实时间差并处理计数器复位')
    root = next(m for m in first['disk']['mounts'] if m['path'] == '/')
    check(root['total'] == psutil.disk_usage('/').total, '根分区容量与操作系统一致')
    if collector.gpu_command:
        check(bool(first['gpus']), 'NVIDIA显卡采集成功')
        gpu = first['gpus'][0]
        check(gpu['name'] == subprocess.check_output(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'], text=True).strip().splitlines()[0], '显卡型号与nvidia-smi一致')
        check(0 <= gpu['usage'] <= 100 and 0 <= gpu['used'] <= gpu['total'], 'GPU利用率和显存有效')
    # Drive one core briefly and prove a newly appearing process becomes measurable.
    busy = subprocess.Popen([sys.executable, '-c', 'import time; end=time.monotonic()+5\nwhile time.monotonic()<end: pass'])
    try:
        collector.sample()
        QTest.qWait(650)
        second = collector.sample()
        process = next(p for p in second['processes'] if p['pid'] == busy.pid)
        check(process['cpu'] > 0, '新进程经过基线采样后出现真实CPU负载')
    finally:
        busy.terminate()
        busy.wait()
    # Generate local network traffic and verify interface counter deltas.
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    def receive_bytes():
        conn, _ = listener.accept()
        with conn:
            while conn.recv(65536):
                pass
    receiver = threading.Thread(target=receive_bytes)
    receiver.start()
    with socket.create_connection(listener.getsockname()) as sender:
        sender.sendall(b'x'*(2*1024**2))
    receiver.join()
    listener.close()
    QTest.qWait(150)
    third = collector.sample()
    lo = next(i for i in third['network']['interfaces'] if i['name'] == 'lo')
    check(lo['down'] > 0 and lo['up_rate'] > 0, '真实网络流量能产生接口速率')
    for _ in range(6):
        window.receive(collector.sample())
        QTest.qWait(250)
    check(len(window.history) == 7, '曲线仅保存实际采样，没有伪造启动历史')
    window.navigate('processes')
    window.search.setText(str(os.getpid()))
    check(any(window.proxy.index(i, 1).data() == str(os.getpid()) for i in range(window.proxy.rowCount())), '进程搜索能找到当前真实PID')
    window.search.setText('pulse-no-such-process-829193')
    check(window.proxy.rowCount() == 0, '进程无匹配时返回空列表')
    window.search.clear()
    window.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
    QTest.qWait(100)
    rss = [window.proxy.index(i, 3).data(Qt.ItemDataRole.UserRole) for i in range(window.proxy.rowCount())]
    check(rss == sorted(rss, reverse=True), '内存按数值排序')
    window.table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
    for page in ('overview', 'processes', 'cpu', 'memory', 'gpu', 'disk', 'network', 'settings', 'panel'):
        window.navigate(page)
        QTest.qWait(50)
        check(window.heading.text() != '' and window.stack.currentWidget() is window.pages[page], f'{page}页面实际切换')
        window.grab().save(str(OUT/f'{page}.png'))
    window.panel_style.setCurrentIndex(window.panel_style.findData('bars'))
    window.panel_position.setCurrentIndex(window.panel_position.findData('right'))
    window.panel_width.setValue(70)
    window.panel_color.setChecked(False)
    window.panel_fields['gpu'].setChecked(False)
    config = read_panel(settings)
    check(config['style'] == 'bars' and config['position'] == 'right' and config['width'] == 70 and not config['color'] and not config['fields']['gpu'], '顶栏设置控件保存位置、样式、宽度、配色及项目')
    window.panel_style.setCurrentIndex(window.panel_style.findData('graphs'))
    window.panel_position.setCurrentIndex(window.panel_position.findData('left'))
    window.panel_width.setValue(50)
    window.panel_color.setChecked(True)
    window.panel_fields['gpu'].setChecked(True)
    window.toggle_widget(True)
    QTest.qWait(100)
    check(window.widget.isVisible(), '小组件显示')
    window.set_widget_mode('top')
    QTest.qWait(100)
    check(bool(window.widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint), '小组件置顶模式')
    if app.platformName() == 'xcb':
        properties = subprocess.check_output(['xprop', '-id', hex(int(window.widget.windowHandle().winId())), '_NET_WM_STATE'], text=True)
        check('_NET_WM_STATE_ABOVE' in properties, 'X11窗口管理器实际接受置顶状态')
    window.set_widget_mode('desktop')
    QTest.qWait(100)
    check(bool(window.widget.windowFlags() & Qt.WindowType.WindowStaysOnBottomHint), '小组件桌面模式')
    if app.platformName() == 'xcb':
        properties = subprocess.check_output(['xprop', '-id', hex(int(window.widget.windowHandle().winId())), '_NET_WM_STATE'], text=True)
        check('_NET_WM_STATE_BELOW' in properties, 'X11窗口管理器实际接受桌面下层状态')
        properties = subprocess.check_output(['xprop', '-id', hex(int(window.widget.windowHandle().winId())), '_NET_WM_WINDOW_TYPE', '_NET_WM_DESKTOP'], text=True)
        check('_NET_WM_WINDOW_TYPE_DESKTOP' not in properties, '小组件保持可交互窗口类型，避免桌面图标层拦截')
    window.navigate('cpu')
    check(window.cpu_grid.values == window.snapshot['cpus'], 'CPU核心图逐项绑定真实逻辑核心数据')
    window.navigate('gpu')
    check(window.gpu_gauge.value == gpu_usage(window.snapshot), 'GPU环图绑定真实利用率')
    check(window.widget.core_grid.values == window.snapshot['cpus'], '小组件显示全部逻辑核心')
    check(window.widget.gpu_gauge.value == gpu_usage(window.snapshot), '小组件GPU环图绑定真实利用率')
    if app.platformName() == 'xcb':
        # XTest sends events through X11 hit testing, unlike QTest direct delivery.
        def pump():
            loop = QEventLoop()
            QTimer.singleShot(150, loop.quit)
            loop.exec()
        def pointer_at(control, pos=None):
            point = control.mapToGlobal(pos or control.rect().center())
            scale = control.devicePixelRatioF()
            subprocess.run(['xdotool', 'mousemove', str(round(point.x()*scale)), str(round(point.y()*scale))], check=True)
            pump()
        def click(control):
            pointer_at(control)
            subprocess.run(['xdotool', 'click', '1'], check=True)
            pump()
        window.hide()
        window.set_widget_mode('normal')
        window.widget.raise_()
        window.widget.activateWindow()
        pump()
        old_pos = window.widget.pos()
        pointer_at(window.widget, QPoint(50, 22))
        subprocess.run(['xdotool', 'mousedown', '1'], check=True)
        pump()
        subprocess.run(['xdotool', 'mousemove_relative', '--', '80', '50'], check=True)
        pump()
        subprocess.run(['xdotool', 'mouseup', '1'], check=True)
        pump()
        check(window.widget.pos() != old_pos, 'X11实际鼠标拖动小组件成功')
        click(window.widget.menu_button)
        check(window.widget.active_menu.isVisible(), 'X11实际鼠标点击可打开小组件菜单')
        menu = window.widget.active_menu
        action = next(a for a in menu.actions() if a.text() == '悬浮置顶')
        pointer_at(menu, menu.actionGeometry(action).center())
        subprocess.run(['xdotool', 'click', '1'], check=True)
        pump()
        check(settings.value('widget_mode') == 'top', 'X11实际鼠标选择菜单可切换置顶')
        click(window.widget.open_button)
        check(window.isVisible(), 'X11实际鼠标按钮能打开主窗口')
        window.hide()
        window.set_widget_mode('normal')
        window.widget.raise_()
        window.widget.activateWindow()
        pump()
        click(window.widget.menu_button)
        check(window.widget.active_menu.isVisible(), '切换回普通悬浮后实际接收鼠标菜单点击')
        window.widget.active_menu.hide()
        window.set_widget_mode('desktop')
        window.show_main()
    window.opacity_slider.setValue(80)
    check(abs(window.widget.windowOpacity()-.8) < .01 and settings.value('widget_opacity', 0, int) == 80, '透明度应用并保存')
    window.opacity_slider.setValue(95)
    window.interval_combo.setCurrentIndex(2)
    check(settings.value('interval', 0, int) == 5, '刷新间隔保存')
    window.interval_combo.setCurrentIndex(0)
    window.widget.grab().save(str(OUT/'widget.png'))
    old_pos = window.widget.pos()
    QTest.mousePress(window.widget, Qt.MouseButton.LeftButton, pos=QPoint(60, 20))
    QTest.mouseMove(window.widget, QPoint(100, 60))
    QTest.mouseRelease(window.widget, Qt.MouseButton.LeftButton)
    check(window.widget.pos() != old_pos, '小组件顶部可拖动')
    window.navigate('overview')
    window.resize(980, 740)
    QTest.qWait(100)
    window.grab().save(str(OUT/'overview-minimum.png'))
    window.resize(1160, 850)
    window.toggle_pause()
    value = window.metrics['cpu'].value.text()
    frozen_chart = list(window.overview_chart.history)
    window.receive(collector.sample())
    check(window.metrics['cpu'].value.text() == value, '暂停时主窗口数值保持')
    check(list(window.overview_chart.history) == frozen_chart, '暂停时曲线也保持，窗口重绘不会刷新历史')
    check(window.widget.footer.text().endswith(__import__('datetime').datetime.fromtimestamp(window.snapshot['wall_time']).strftime('%H:%M:%S')), '暂停主窗口时小组件仍接收数据')
    window.toggle_pause()
    for _ in range(200):
        window.overview_chart.grab()
    check(True, '趋势图连续200次真实绘制完成')
    window.close()
    check(window.widget.isVisible() and not window.isVisible(), '关闭主窗口后小组件继续运行')
    window.show_main()
    check(window.isVisible(), '小组件可重新打开主窗口')
    window.autostart_path = Path(temp)/'autostart/pulse-monitor.desktop'
    window.service_path = Path(temp)/'absent-pulse-monitor.service'
    window.change_autostart(True)
    check('--widget' in window.autostart_path.read_text(), '可选自启动写入正确的小组件入口')
    window.change_autostart(False)
    check(not window.autostart_path.exists(), '关闭自启动清理专属入口')
    window.toggle_widget(False)
    check(not window.widget.isVisible(), '小组件隐藏')
    worker_samples, worker_errors = [], []
    worker = Sampler(.2)
    worker.sampled.connect(worker_samples.append)
    worker.sampled.connect(window.receive)
    worker.failed.connect(worker_errors.append)
    window.interval_changed.connect(worker.set_interval)
    worker.start()
    try:
        loop = QEventLoop()
        QTimer.singleShot(1800, loop.quit)
        loop.exec()
        check(len(worker_samples) >= 3 and not worker_errors, '后台线程持续采集并向界面交付真实数据')
        window.interval_combo.setCurrentIndex(1)
        check(worker.interval == 2, '设置页刷新间隔实际传递到采集线程')
        window.interval_combo.setCurrentIndex(0)
    finally:
        worker.stop()
    check(not worker.isRunning(), '采集线程可完整退出')
    settings.sync()
    reloaded = QSettings(str(Path(temp)/'settings.ini'), QSettings.Format.IniFormat)
    check(reloaded.value('widget_opacity', 0, int) == 95 and reloaded.value('widget_mode') == 'desktop', '设置重新读取一致')
    window.hide()
    window.widget.hide()

(OUT/'verification.json').write_text(json.dumps(dict(checks=checks, count=len(checks),
    platform=app.platformName(), gpu=first['gpus'], cpu=first['cpu_name'],
    versions=dict(python=sys.version.split()[0], psutil=psutil.__version__, pyside=__import__('PySide6').__version__)), ensure_ascii=False, indent=2))
print(f'{len(checks)} checks passed; screenshots and report: {OUT}')
