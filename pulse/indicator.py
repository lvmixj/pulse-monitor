"""GNOME top-panel indicator using the OS Ayatana library, outside Qt."""
import json
import logging
import os
import signal
import subprocess
import time
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import AyatanaAppIndicator3 as AppIndicator, GLib, Gtk

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))/'pulse-monitor.json'


def rate(value):
    if value >= 1024**2:
        return f'{value/1024**2:.1f}M'
    return f'{value/1024:.0f}K'


def command(*args):
    # Forward directly to the existing sampler; no launch of a second backend.
    subprocess.Popen([str(ROOT/'.venv/bin/python'), '-m', 'pulse', '--client', *args], cwd=ROOT)


def main():
    logging.basicConfig(level=logging.INFO)
    indicator = AppIndicator.Indicator.new('pulse-monitor', str(ROOT/'assets/pulse.svg'), AppIndicator.IndicatorCategory.SYSTEM_SERVICES)
    indicator.set_title('Pulse 系统资源监控')
    indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
    menu = Gtk.Menu()
    summary = Gtk.MenuItem(label='正在连接Pulse后台…')
    summary.set_sensitive(False)
    menu.append(summary)
    gpu_details = Gtk.MenuItem(label='GPU：等待采样')
    gpu_details.set_sensitive(False)
    menu.append(gpu_details)
    menu.append(Gtk.SeparatorMenuItem())
    for title, args in [('打开系统总览', ()), ('查看CPU各核心', ('--page', 'cpu')),
                        ('查看GPU利用率', ('--page', 'gpu')), ('设置与小组件', ('--page', 'settings'))]:
        item = Gtk.MenuItem(label=title)
        item.connect('activate', lambda item, argv=args: command(*argv))
        menu.append(item)
    widget = Gtk.MenuItem(label='显示/隐藏桌面小组件')
    widget.connect('activate', lambda item: command('--toggle-widget'))
    menu.append(widget)
    menu.append(Gtk.SeparatorMenuItem())
    quit_item = Gtk.MenuItem(label='退出Pulse监控')
    quit_item.connect('activate', lambda item: command('--quit'))
    menu.append(quit_item)
    menu.show_all()
    indicator.set_menu(menu)
    indicator.set_label('Pulse · 正在采样', '')
    logged_error = None

    def update():
        nonlocal logged_error
        try:
            data = json.loads(SNAPSHOT.read_text())
            age = time.time()-data['wall_time']
            if age > 10:
                indicator.set_label('Pulse · 数据已中断', '')
                summary.set_label(f'上次更新{age:.0f}秒前，请检查后台服务')
                return GLib.SOURCE_CONTINUE
            gpu = data['gpu']
            gpu_usage = f"{gpu['usage']:.0f}%" if gpu and gpu['usage'] is not None else '—'
            frequency = f"[{data['frequency']/1000:.2f}GHz]" if data.get('frequency') else ''
            used_vram = f"[{gpu['used']/1024:.1f}G]" if gpu and gpu['used'] is not None else ''
            text = (f"内存 {data['memory_used']/1024**3:.1f}G  "
                    f"↓{rate(data['down'])} ↑{rate(data['up'])}  "
                    f"CPU {data['cpu']:.0f}%{frequency}  GPU {gpu_usage}{used_vram}")
            indicator.set_label(text, '')
            summary.set_label(f"CPU {data['cpu']:.1f}% · 内存 {data['memory_percent']:.1f}% · {data['cores']}线程")
            if gpu:
                vram = f"{gpu['used']/1024:.1f}/{gpu['total']/1024:.1f}GiB" if gpu['used'] is not None and gpu['total'] else '暂无读数'
                temp = f"{gpu['temperature']:.0f}°C" if gpu['temperature'] is not None else '暂无读数'
                gpu_details.set_label(f"GPU {gpu_usage} · 显存{vram} · {temp}")
            else:
                gpu_details.set_label('GPU暂无读数')
            widget.set_label('隐藏桌面小组件' if data['widget_visible'] else '显示桌面小组件')
            logged_error = None
        except (OSError, ValueError, KeyError, TypeError) as error:
            indicator.set_label('Pulse · 等待后台', '')
            if str(error) != logged_error:
                logging.warning('Panel snapshot unavailable: %s', error)
                logged_error = str(error)
        return GLib.SOURCE_CONTINUE

    timer = GLib.timeout_add_seconds(1, update)
    for sig in (signal.SIGTERM, signal.SIGINT):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, lambda: (Gtk.main_quit(), GLib.SOURCE_REMOVE)[1])
    update()
    logging.info('Pulse panel indicator ready')
    Gtk.main()
    GLib.source_remove(timer)
    indicator.set_status(AppIndicator.IndicatorStatus.PASSIVE)


if __name__ == '__main__':
    main()
