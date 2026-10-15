#!/bin/sh
set -eu
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$APP_DIR"
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    echo '请先按README安装项目依赖。' >&2
    exit 1
fi
if [ "${1:-}" = "--backend" ]; then
    exec "$APP_DIR/.venv/bin/python" -m pulse --background
fi
if [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/pulse-monitor.service" ]; then
    systemctl --user start pulse-monitor.service
    exec "$APP_DIR/.venv/bin/python" -m pulse --client "$@"
fi
exec "$APP_DIR/.venv/bin/python" -m pulse "$@"
