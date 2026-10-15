#!/usr/bin/env python3
"""Install or remove Pulse's per-user desktop integration from this checkout."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from pulse.desktop import desktop_entry

ROOT = Path(__file__).resolve().parent
UUID = 'pulse-panel@local'


def systemd_quote(path, command=False):
    text = str(path).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    if command:
        text = text.replace('$', '$$')
    return '"'+text+'"'


def write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    path.chmod(mode)
    print(path)


def main():
    parser = argparse.ArgumentParser(description='安装Pulse用户级桌面入口；源码和.venv保留在当前目录')
    parser.add_argument('--uninstall', action='store_true', help='停止Pulse并移除桌面集成，保留源码、依赖与偏好')
    args = parser.parse_args()
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))
    service = config/'systemd/user/pulse-monitor.service'
    application = data/'applications/pulse-monitor.desktop'
    launcher = data/'pulse-monitor/launch'
    extension = data/'gnome-shell/extensions'/UUID
    if args.uninstall:
        if service.exists():
            subprocess.run(['systemctl', '--user', 'disable', '--now', 'pulse-monitor.service'], check=True)
        if extension.exists() and shutil.which('gnome-extensions'):
            enabled = subprocess.check_output(['gnome-extensions', 'list', '--enabled'], text=True).splitlines()
            if UUID in enabled:
                subprocess.run(['gnome-extensions', 'disable', UUID], check=True)
        for path in (service, application, launcher, config/'autostart/pulse-monitor.desktop'):
            path.unlink(missing_ok=True)
        if extension.exists():
            shutil.rmtree(extension)
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        print('已移除Pulse桌面集成，源码、.venv和用户偏好已保留。')
        return
    if any(c in str(ROOT) for c in ('\n', '\r', '\t')):
        parser.error('项目路径不能包含换行符或制表符。')
    python = ROOT/'.venv/bin/python'
    if not python.is_file():
        parser.error('请先按照README创建.venv并安装requirements.txt。')
    subprocess.run([str(python), '-c', 'import PySide6.QtWidgets, psutil'], check=True)
    # ZIP downloads and browser uploads can omit the executable bit.
    (ROOT/'run.sh').chmod((ROOT/'run.sh').stat().st_mode | 0o100)
    template = (ROOT/'desktop/pulse-monitor.service').read_text()
    service_text = template.replace('@RUN_SCRIPT@', systemd_quote(ROOT/'run.sh', command=True))
    write(service, service_text)
    write(application, desktop_entry(root=ROOT))
    write(launcher, '#!/bin/sh\nexec '+shlex.quote(str(ROOT/'run.sh'))+' "$@"\n', 0o755)
    if shutil.which('gnome-shell'):
        version = subprocess.check_output(['gnome-shell', '--version'], text=True).strip().split()[-1]
        if version.split('.')[0] == '42':
            extension.mkdir(parents=True, exist_ok=True)
            for source in (ROOT/'desktop'/UUID).iterdir():
                if source.suffix in ('.js', '.json'):
                    shutil.copy2(source, extension/source.name)
            print('已安装GNOME42顶栏组件；首次安装后请重新登录，再启用'+UUID+'。')
        else:
            print('当前GNOME版本为'+version+'；图形顶栏支持GNOME42，数字顶栏使用AppIndicator。')
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    print('安装完成。运行./run.sh打开窗口；登录自启动：systemctl --user enable --now pulse-monitor.service')


if __name__ == '__main__':
    main()
