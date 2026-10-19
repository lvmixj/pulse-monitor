"""Skin/state contract and blank-page regressions, isolated from user preferences."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pulse.collector import Collector
from pulse.theme import THEMES, PALETTES, apply_theme
from pulse.ui import MainWindow, gpu_usage

ROOT = Path(__file__).resolve().parents[1]
app = QApplication([])
app.setStyle('Fusion')
app.setQuitOnLastWindowClosed(False)
checks = []
def check(condition, title):
    assert condition, title
    checks.append(title)
    print('PASS', title, flush=True)

def contrast(a, b):
    def luminance(value):
        values = [int(value[i:i+2], 16)/255 for i in (1, 3, 5)]
        return sum(weight*(v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4)
                   for v, weight in zip(values, (.2126, .7152, .0722)))
    low, high = sorted((luminance(a), luminance(b)))
    return (high+.05)/(low+.05)

with tempfile.TemporaryDirectory(prefix='pulse-theme-') as tmp:
    path = str(Path(tmp)/'settings.ini')
    settings = QSettings(path, QSettings.Format.IniFormat)
    settings.setValue('widget_opacity', 100)
    w = MainWindow(settings)
    w.setWindowTitle('Pulse theme verification')
    w.show()
    w.activateWindow()
    QTest.qWait(30)
    check(not w.pause_button.isEnabled(), '首个采样前暂停按钮禁用')
    w.toggle_pause()
    w.theme_combo.setCurrentIndex(w.theme_combo.findData('light'))
    collector = Collector()
    first = collector.sample()
    w.receive(first)
    w.navigate('memory')
    check(not w.paused and w.pause_button.isEnabled() and 'GiB' in w.resource_details['memory'].text(),
          '复现路径已修复：首采样前暂停与换肤后内存页显示真实读数')
    check('物理内存总量' in w.resource_body['memory'].text() and '更新于' in w.status.text(), '首个采样后的详情与更新时间正确')
    w.toggle_widget(True)
    w.toggle_pause()
    frozen = w.monitor.display
    frozen_history = list(w.resource_charts['memory'].history)
    QTest.qWait(70)
    second = collector.sample()
    w.receive(second)
    check(w.snapshot is second and w.monitor.display is first, '暂停保存首个真实快照，实时采样继续更新')
    for name, palette in PALETTES.items():
        check(set(palette) == set(PALETTES['ocean']), name+'实现相同的语义配色契约')
        for text in ('text', 'muted', 'cpu', 'memory', 'gpu', 'success', 'warning'):
            check(contrast(palette[text], palette['surface']) >= 4.5, name+'/'+text+'文字对比度≥4.5:1')
        check(contrast(palette['on_primary'], palette['primary']) >= 4.5, name+'主要按钮文字对比度≥4.5:1')
        ids = (id(w.monitor), id(w.monitor.latest), id(w.monitor.display), id(w.history), id(w.stack))
        widgets = {key: id(widget) for key, widget in w.pages.items()}
        original_preferences = {key: settings.value(key) for key in settings.allKeys() if key != 'theme'}
        w.theme_combo.setCurrentIndex(w.theme_combo.findData(name))
        QTest.qWait(20)
        check(ids == (id(w.monitor), id(w.monitor.latest), id(w.monitor.display), id(w.history), id(w.stack)) and
              widgets == {key: id(widget) for key, widget in w.pages.items()}, name+'换肤保留状态、快照和所有页面实例')
        check(original_preferences == {key: settings.value(key) for key in settings.allKeys() if key != 'theme'}, name+'换肤仅写主题偏好')
        check(QSettings(path, QSettings.Format.IniFormat).value('theme') == name, name+'选择立即保存')
        for page in ('overview', 'cpu', 'memory', 'gpu', 'disk', 'network', 'processes'):
            w.navigate(page)
            QTest.qWait(5)
            if page in w.resource_details:
                check('等待' not in w.resource_details[page].text() and '等待首个' not in w.resource_body[page].text(), name+'/'+page+'暂停导航显示快照内容')
            elif page == 'processes':
                check(w.process_model.rowCount() == len(frozen['processes']), name+'暂停进程页仍有数据')
            else:
                check(w.metrics['cpu'].value.text() == f"{frozen['cpu']:.1f}%", name+'暂停总览仍有真实读数')
            w.grab().save(str(ROOT/f'artifacts/rework-{name}-{page}.png'))
        check(w.cpu_grid.values == frozen['cpus'] and w.gpu_gauge.value == gpu_usage(frozen), name+'CPU逐核心与GPU仪表绑定同一快照')
        check(list(w.overview_chart.history) == frozen_history and list(w.resource_charts['memory'].history) == frozen_history,
              name+'换肤与导航保持冻结曲线')
        check(w.widget.core_grid.values == second['cpus'] and w.widget.gpu_gauge.value == gpu_usage(second), name+'桌面组件保持最新采样')
        check(w.paused and '后台采集中' in w.live.text() and '快照时间' in w.status.text(), name+'暂停状态及快照时间清晰显示')
        w.widget.grab().save(str(ROOT/f'artifacts/rework-{name}-widget.png'))
        w.navigate('settings')
        w.grab().save(str(ROOT/f'artifacts/rework-{name}-settings.png'))
    w.toggle_pause()
    w.navigate('memory')
    check(w.monitor.display is second and w.resource_charts['memory'].history is w.history and '更新于' in w.status.text(), '继续显示恢复最新采样与实时曲线')
    w.navigate('settings')
    # Space belongs to the control; it is not the global pause command.
    w.theme_combo.setFocus()
    QTest.keyClick(w.theme_combo, Qt.Key.Key_Space)
    QTest.keyClick(w.theme_combo, Qt.Key.Key_Escape)
    check(not w.paused, '主题下拉框空格操作不会暂停监控')
    w.navigate('processes')
    w.search.setFocus()
    QTest.keyClicks(w.search, 'test process')
    check(w.search.text() == 'test process' and not w.paused, '搜索输入空格不会暂停监控')
    w.search.clear()
    for name in THEMES:
        apply_theme(app, name)
        w.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        app.processEvents()
        values = [w.proxy.index(i, 3).data(Qt.ItemDataRole.UserRole) for i in range(w.proxy.rowCount())]
        check(values == sorted(values, reverse=True), name+'进程内存数值排序正常')
    w.theme_combo.setCurrentIndex(w.theme_combo.findData('light'))
    w.close()
    check(w.widget.isVisible() and not w.isVisible(), '关闭主窗口保留小组件')
    w.show_main()
    check(w.isVisible() and w.snapshot is second, '重新打开保留数据')
    w.widget.hide()
    w.hide()
    restored = MainWindow(QSettings(path, QSettings.Format.IniFormat))
    check(restored.theme_combo.currentData() == 'light' and app.property('pulseTheme') == 'light', '重新创建窗口恢复保存主题')
    restored.resize(980, 740)
    restored.show()
    restored.navigate('settings')
    QTest.qWait(20)
    check(restored.theme_combo.isVisible() and restored.theme_combo.height() > 0, '最小桌面窗口可见主题入口')
    restored.hide()
(ROOT/'artifacts/theme-verification.json').write_text(json.dumps({'count':len(checks),'checks':checks},ensure_ascii=False,indent=2))
print(f'{len(checks)} skin and state checks passed')
