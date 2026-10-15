"""Desktop entry generation, shared by the installer and login autostart."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def desktop_entry(widget=False, root=ROOT):
    # Exec quoting is applied before the desktop-entry string escaping layer.
    command = str(root/'run.sh').replace('%', '%%')
    for character in ('\\', '"', '`', '$'):
        command = command.replace(character, '\\'+character)
    command = ('"'+command+'"').replace('\\', '\\\\')
    icon = str(root/'assets/pulse.svg').replace('\\', '\\\\')
    return f'''[Desktop Entry]
Type=Application
Name=Pulse 系统资源监控
Comment=本机资源监控与桌面小组件
Exec={command}{' --widget' if widget else ''}
Icon={icon}
Terminal=false
Categories=System;Monitor;
StartupWMClass=pulse-monitor
'''
