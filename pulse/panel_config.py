"""Shared panel preferences serialized into the local telemetry snapshot."""
FIELDS = [('cpu', 'CPU利用率'), ('frequency', 'CPU频率'), ('memory', '内存容量'),
          ('network', '网络速率'), ('gpu', 'GPU利用率'), ('vram', '显存容量'),
          ('temperature', 'GPU温度')]


def read_panel(settings):
    settings.sync()
    return dict(position=settings.value('panel_position', 'left'),
                style=settings.value('panel_style', 'graphs'),
                color=settings.value('panel_color', True, bool),
                width=settings.value('panel_width', 50, int),
                fields={key: settings.value('panel_show_'+key, key != 'temperature', bool) for key, _ in FIELDS})
