"""Opt-in live GNOME panel acceptance checks; restore user's panel preferences."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pulse.panel_config import FIELDS
RUNTIME = Path(os.environ['XDG_RUNTIME_DIR'])
MARKER = RUNTIME/'pulse-panel-native.json'
STATE = RUNTIME/'pulse-monitor.json'


def main():
    app = QApplication.instance() or QApplication([])
    settings = QSettings('Pulse', 'ResourceMonitor')
    keys = ['panel_position', 'panel_style', 'panel_width', 'panel_color']+['panel_show_'+k for k, _ in FIELDS]
    original = {k: settings.value(k) for k in keys}
    checks = []
    def check(condition, title):
        assert condition, title
        checks.append(title)
        print('PASS', title, flush=True)
    def read(path):
        return json.loads(path.read_text())
    def wait_for(predicate):
        deadline = time.monotonic()+12
        while time.monotonic() < deadline:
            try:
                value = predicate()
                if value:
                    return value
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            time.sleep(.15)
        raise AssertionError('Panel did not apply the expected live state')
    def apply(**kwargs):
        for key, value in kwargs.items():
            settings.setValue('panel_'+key, value)
        settings.sync()
    def run(*args):
        subprocess.run([str(ROOT/'run.sh'), *args], check=True, timeout=10)
    tray_before = subprocess.check_output(['gsettings', 'get', 'org.gnome.shell.extensions.appindicator', 'tray-pos'], text=True)
    try:
        check(time.time()-MARKER.stat().st_mtime < 5, '原生顶栏组件持续刷新')
        apply(position='left', style='graphs')
        wait_for(lambda: read(MARKER)['position']=='left' and read(MARKER)['style']=='graphs')
        left = read(MARKER)['x']
        check(left < 500, 'Pulse独立位于左侧')
        for style in ['graphs', 'bars', 'numbers']:
            apply(style=style)
            wait_for(lambda: read(MARKER)['style']==style)
            check(True, f'顶栏实时切换{style}样式')
            app.primaryScreen().grabWindow(0, 0, 0, 1000, 45).save(str(ROOT/f'artifacts/panel-{style}.png'))
        apply(show_gpu=False, show_frequency=False, show_temperature=True)
        wait_for(lambda: 'gpu' not in read(MARKER)['fields'] and 'frequency' not in read(MARKER)['fields'] and 'temperature' in read(MARKER)['fields'])
        check(True, '顶栏选择显示项目实际生效')
        apply(position='right')
        wait_for(lambda: read(MARKER)['position']=='right' and read(MARKER)['x']>left+500)
        check(True, '仅Pulse移动到右侧')
        apply(position='center')
        wait_for(lambda: read(MARKER)['position']=='center')
        check(True, '顶栏支持中间位置')
        apply(position='left', style='graphs', width=70, color=False)
        wait_for(lambda: read(STATE)['panel']['width']==70 and not read(STATE)['panel']['color'])
        check(True, '宽度和配色设置传递到顶栏采样契约')
        check(subprocess.check_output(['gsettings', 'get', 'org.gnome.shell.extensions.appindicator', 'tray-pos'], text=True)==tray_before, '其他托盘图标的位置设置保持不变')
        run('--page', 'panel')
        wait_for(lambda: read(STATE)['page']=='panel' and read(STATE)['window_visible'])
        check(True, '顶栏设置页面实际可打开')
        # The native panel survives a backend crash and reconnects to new data.
        old = read(STATE)['pid']
        os.kill(old, signal.SIGKILL)
        wait_for(lambda: read(STATE)['pid']!=old and time.time()-read(STATE)['wall_time']<3)
        wait_for(lambda: abs(read(MARKER)['lastTime']-read(STATE)['wall_time'])<3)
        check(True, '异常重启后原生顶栏继续显示新采样')
    finally:
        for key, value in original.items():
            if value is None:
                settings.remove(key)
            else:
                settings.setValue(key, value)
        settings.sync()
    wait_for(lambda: read(MARKER)['position']==read(STATE)['panel']['position'] and read(MARKER)['style']==read(STATE)['panel']['style'])
    report = dict(checks=checks, count=len(checks), final_marker=read(MARKER), final_state=read(STATE))
    (ROOT/'artifacts/panel-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f'{len(checks)} native panel checks passed')


if __name__ == '__main__':
    main()
