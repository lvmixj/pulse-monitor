from collections import deque
from datetime import datetime
from pathlib import Path
import os
import subprocess

from PySide6.QtCore import QPoint, QSettings, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QPushButton, QScrollArea,
    QSlider, QStackedWidget, QTableView, QVBoxLayout, QWidget, QProgressBar,
)

from .charts import Chart, CoreGrid, UsageGauge
from .collector import byte_text
from .processes import ProcessModel
from .panel_config import FIELDS, read_panel
from .desktop import desktop_entry
from .theme import BASE, COLORS, MUTED

ROOT = Path(__file__).resolve().parent.parent
TITLES = {'cpu': 'CPU', 'memory': '内存', 'gpu': 'GPU', 'disk': '磁盘', 'network': '网络'}


def label(text='', kind=None):
    w = QLabel(text)
    if kind:
        w.setObjectName(kind)
    return w


def button(text, callback, kind=None):
    w = QPushButton(text)
    if kind:
        w.setObjectName(kind)
    w.setCursor(Qt.CursorShape.PointingHandCursor)
    w.clicked.connect(callback)
    return w


def panel():
    w = QFrame()
    w.setObjectName('panel')
    layout = QVBoxLayout(w)
    layout.setContentsMargins(22, 18, 22, 18)
    layout.setSpacing(12)
    return w, layout


def duration(seconds):
    hours = int(seconds) // 3600
    return f'{hours//24}天{hours%24}小时' if hours >= 24 else f'{hours}小时{int(seconds)%3600//60}分钟'


def gpu_usage(snapshot):
    return snapshot['gpus'][0]['usage'] if snapshot['gpus'] else None


def temperature(value):
    return f'{value:.0f}°C' if value is not None else '暂无读数'


class Metric(QFrame):
    clicked = Signal(str)

    def __init__(self, key, history):
        super().__init__()
        self.key = key
        self.setObjectName('metric')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f'查看{TITLES[key]}详情')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(3)
        header = QHBoxLayout()
        name = label(TITLES[key], 'section')
        name.setStyleSheet(f'color: {COLORS[key]};')
        header.addWidget(name)
        header.addStretch()
        self.status = label('等待采样', 'muted')
        header.addWidget(self.status)
        layout.addLayout(header)
        self.value = label('—', 'value')
        layout.addWidget(self.value)
        self.detail = label('', 'muted')
        layout.addWidget(self.detail)
        self.chart = Chart([key], [COLORS[key]], history, compact=True)
        layout.addWidget(self.chart)
        for w in (name, self.status, self.value, self.detail, self.chart):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)

    def refresh(self, s):
        if self.key == 'cpu':
            value = s['cpu']
            self.detail.setText(f"{s['cores']}线程   {temperature(s['temperature'])}")
            self.status.setText('高负载' if value >= 85 else '实时')
        elif self.key == 'memory':
            value = s['memory']['percent']
            self.detail.setText(f"{byte_text(s['memory']['used'])} / {byte_text(s['memory']['total'])}")
            self.status.setText('使用较高' if value >= 85 else '实时')
        else:
            value = gpu_usage(s)
            if s['gpus']:
                gpu = s['gpus'][0]
                vram = f"{gpu['used']/1024:.1f} GiB显存" if gpu['used'] is not None else '显存暂无读数'
                self.detail.setText(f"{vram}   {temperature(gpu['temperature'])}")
            else:
                self.detail.setText('打开详情查看采集状态')
            self.status.setText('高负载' if value is not None and value >= 85 else ('实时' if value is not None else '不可用'))
        self.value.setText(f'{value:.1f}%' if value is not None else '—')
        self.chart.update()


class DesktopWidget(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.settings = main.settings
        self.drag_offset = None
        self.setWindowTitle('Pulse桌面小组件')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 15, 22, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = label('◉  Pulse', 'section')
        title.setStyleSheet('color: #90cbff; font-size: 17px;')
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header.addWidget(title)
        header.addStretch()
        self.mode_label = label('桌面', 'muted')
        self.mode_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header.addWidget(self.mode_label)
        self.menu_button = button('•••', self.show_menu, 'small')
        self.menu_button.setToolTip('小组件菜单：模式、打开主窗口、退出')
        header.addWidget(self.menu_button)
        layout.addLayout(header)
        self.host = label('正在连接本机…', 'muted')
        self.host.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.host)
        row = QHBoxLayout()
        self.metrics = {}
        for key in ('cpu', 'memory', 'gpu'):
            col = QVBoxLayout()
            name = label(TITLES[key])
            name.setStyleSheet(f'color: {COLORS[key]};')
            value = label('—')
            value.setStyleSheet('font-size: 24px; font-weight: 600;')
            col.addWidget(name)
            col.addWidget(value)
            self.metrics[key] = value
            row.addLayout(col)
        layout.addLayout(row)
        gpu_row = QHBoxLayout()
        self.gpu_gauge = UsageGauge(COLORS['gpu'], 78)
        gpu_row.addWidget(self.gpu_gauge)
        gpu_info = QVBoxLayout()
        gpu_info.addWidget(label('GPU利用率', 'section'))
        self.gpu_detail = label('等待采样', 'muted')
        gpu_info.addWidget(self.gpu_detail)
        gpu_row.addLayout(gpu_info, 1)
        layout.addLayout(gpu_row)
        layout.addWidget(label('CPU各逻辑核心', 'muted'))
        self.core_grid = CoreGrid(compact=True)
        layout.addWidget(self.core_grid)
        self.chart = Chart(['cpu', 'memory', 'gpu'], [COLORS[k] for k in ('cpu', 'memory', 'gpu')], main.history, compact=True)
        self.chart.setFixedHeight(67)
        layout.addWidget(self.chart)
        self.net = label('↓ —     ↑ —')
        layout.addWidget(self.net)
        self.footer = label('等待第一个采样', 'muted')
        layout.addWidget(self.footer)
        bottom = QHBoxLayout()
        self.open_button = button('打开监控窗口', main.show_main, 'small')
        bottom.addWidget(self.open_button)
        bottom.addStretch()
        tip = label('拖动顶部移动', 'muted')
        tip.setStyleSheet('font-size: 11px; color: #a2b3c8;')
        bottom.addWidget(tip)
        layout.addLayout(bottom)
        self.apply_mode()
        self.setWindowOpacity(self.settings.value('widget_opacity', 95, int)/100)
        pos = self.settings.value('widget_pos', None)
        screen = QApplication.primaryScreen().availableGeometry()
        if isinstance(pos, QPoint) and any(s.availableGeometry().intersects(self.rect().translated(pos)) for s in QApplication.screens()):
            self.move(pos)
        else:
            self.move(screen.right()-self.width()-26, screen.top()+50)

    def apply_mode(self):
        visible = self.isVisible()
        pos = self.pos()
        mode = self.settings.value('widget_mode', 'normal')
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if mode == 'desktop':
            flags |= Qt.WindowType.WindowStaysOnBottomHint
        elif mode == 'top':
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.mode_label.setText({'desktop': '桌面', 'top': '置顶', 'normal': '悬浮'}[mode])
        self.move(pos)
        if visible:
            self.show()
            if mode != 'desktop':
                self.raise_()
                self.activateWindow()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor('#172538'))
        p.setPen(QPen(QColor('#3b516b'), 1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 20, 20)

    def showEvent(self, event):
        super().showEvent(event)
        # Keep an interactive utility window. GNOME desktop icon surfaces can
        # intercept clicks intended for windows with the DESKTOP type.

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 80:
            self.drag_offset = event.globalPosition().toPoint()-self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            self.move(event.globalPosition().toPoint()-self.drag_offset)

    def mouseReleaseEvent(self, event):
        self.drag_offset = None
        self.settings.setValue('widget_pos', self.pos())

    def show_menu(self):
        menu = QMenu(self)
        self.active_menu = menu
        menu.addAction('打开监控窗口', self.main.show_main)
        menu.addSeparator()
        for text, mode in (('桌面下层', 'desktop'), ('悬浮置顶', 'top'), ('普通悬浮', 'normal')):
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(self.settings.value('widget_mode', 'normal') == mode)
            action.triggered.connect(lambda checked=False, m=mode: self.main.set_widget_mode(m))
        menu.addSeparator()
        menu.addAction('隐藏小组件', lambda: self.main.toggle_widget(False))
        menu.addAction('退出Pulse', QApplication.instance().quit)
        menu.popup(self.menu_button.mapToGlobal(QPoint(0, self.menu_button.height())))

    def refresh(self, s):
        self.host.setText(s['hostname'])
        self.gpu_gauge.set_value(gpu_usage(s))
        gpu = s['gpus'][0] if s['gpus'] else None
        self.gpu_detail.setText(f"{temperature(gpu['temperature'])}   显存{gpu['used']/1024:.1f} GiB" if gpu and gpu['used'] is not None else '暂无显卡读数')
        self.core_grid.set_values(s['cpus'])
        self.adjustSize()
        for key, value in (('cpu', s['cpu']), ('memory', s['memory']['percent']), ('gpu', gpu_usage(s))):
            self.metrics[key].setText(f'{value:.0f}%' if value is not None else '—')
        self.net.setText(f"↓ {byte_text(s['network']['down'], True)}    ↑ {byte_text(s['network']['up'], True)}")
        self.footer.setText(f"运行{duration(s['uptime'])}   {datetime.fromtimestamp(s['wall_time']).strftime('%H:%M:%S')}")
        self.chart.update()

    def closeEvent(self, event):
        self.settings.setValue('widget_pos', self.pos())
        self.main.toggle_widget(False)
        event.accept()


class MainWindow(QMainWindow):
    interval_changed = Signal(float)

    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or QSettings('Pulse', 'ResourceMonitor')
        self.history = deque(maxlen=900)
        self.snapshot = None
        self.paused = False
        self.current_page = 'overview'
        self.resource_charts = {}
        self.resource_details = {}
        self.setWindowTitle('Pulse · 系统资源监控')
        self.setWindowIcon(QIcon(str(ROOT/'assets/pulse.svg')))
        self.resize(1160, 850)
        self.setMinimumSize(980, 740)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(root)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(190)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 26, 16, 20)
        side.setSpacing(6)
        brand = label('◉ Pulse')
        brand.setStyleSheet('font-size: 28px; font-weight: 600; color: #90cbff;')
        side.addWidget(brand)
        side.addWidget(label('看见电脑的每一次呼吸', 'muted'))
        side.addSpacing(25)
        self.nav = {}
        for key, text in [('overview', '▦   总览'), ('processes', '☷   进程'),
                          ('cpu', '◈   CPU'), ('memory', '▤   内存'), ('gpu', '◇   GPU'),
                          ('disk', '▱   磁盘'), ('network', '⇅   网络')]:
            b = button(text, lambda checked=False, k=key: self.navigate(k), 'nav')
            b.setCheckable(True)
            self.nav[key] = b
            side.addWidget(b)
        side.addStretch()
        settings_button = button('⚙   设置与小组件', lambda: self.navigate('settings'), 'nav')
        settings_button.setCheckable(True)
        self.nav['settings'] = settings_button
        side.addWidget(settings_button)
        panel_button = button('▥   顶栏设置', lambda: self.navigate('panel'), 'nav')
        panel_button.setCheckable(True)
        self.nav['panel'] = panel_button
        side.addWidget(panel_button)
        side.addWidget(button('退出Pulse', QApplication.instance().quit, 'small'))
        side.addSpacing(8)
        side.addWidget(label('本机采集 · 数据留在本机', 'muted'))
        layout.addWidget(sidebar)
        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(28, 24, 28, 16)
        main_layout.setSpacing(16)
        header = QHBoxLayout()
        self.heading = label('系统总览', 'title')
        header.addWidget(self.heading)
        header.addStretch()
        self.live = label('●  正在采集', 'muted')
        self.live.setStyleSheet('color: #59d9be;')
        header.addWidget(self.live)
        self.pause_button = button('暂停显示', self.toggle_pause)
        header.addWidget(self.pause_button)
        self.widget_button = button('桌面小组件', lambda: self.toggle_widget(not self.widget.isVisible()), 'primary')
        header.addWidget(self.widget_button)
        main_layout.addLayout(header)
        self.subtitle = label('CPU、显存与网络活动，一眼掌握。', 'muted')
        main_layout.addWidget(self.subtitle)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)
        self.pages = {}
        self.build_overview()
        self.build_processes()
        for key in TITLES:
            self.build_resource(key)
        self.build_settings()
        self.build_panel_settings()
        footer = QHBoxLayout()
        self.status = label('等待首个采样…', 'muted')
        footer.addWidget(self.status)
        footer.addStretch()
        footer.addWidget(label('Ctrl+K 搜索进程   ·   Space 暂停', 'muted'))
        main_layout.addLayout(footer)
        layout.addWidget(main, 1)
        self.widget = DesktopWidget(self)
        self.widget_check.setChecked(self.settings.value('widget_visible', False, bool))
        self.navigate('overview')
        self.search_shortcut = QShortcut(QKeySequence('Ctrl+K'), self)
        self.search_shortcut.activated.connect(self.focus_search)
        self.pause_shortcut = QShortcut(QKeySequence('Space'), self)
        self.pause_shortcut.activated.connect(self.toggle_pause)
        if self.settings.value('geometry'):
            self.restoreGeometry(self.settings.value('geometry'))

    def add_page(self, key, widget):
        self.pages[key] = widget
        self.stack.addWidget(widget)

    def build_overview(self):
        page = QWidget()
        page.setObjectName('page')
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)
        self.metrics = {}
        for column, key in enumerate(('cpu', 'memory', 'gpu')):
            card = Metric(key, self.history)
            card.clicked.connect(self.navigate)
            grid.addWidget(card, 0, column*2, 1, 2)
            self.metrics[key] = card
        trend, area = panel()
        top = QHBoxLayout()
        top.addWidget(label('资源趋势', 'section'))
        top.addStretch()
        self.range_combo = QComboBox()
        for title, seconds in [('最近1分钟', 60), ('最近3分钟', 180), ('最近5分钟', 300)]:
            self.range_combo.addItem(title, seconds)
        self.range_combo.currentIndexChanged.connect(self.change_range)
        top.addWidget(self.range_combo)
        area.addLayout(top)
        legends = QHBoxLayout()
        for key in ('cpu', 'memory', 'gpu'):
            legend = label('● '+TITLES[key])
            legend.setStyleSheet(f'color: {COLORS[key]};')
            legends.addWidget(legend)
        legends.addStretch()
        area.addLayout(legends)
        self.overview_chart = Chart(['cpu', 'memory', 'gpu'], [COLORS[k] for k in ('cpu', 'memory', 'gpu')], self.history)
        area.addWidget(self.overview_chart, 1)
        grid.addWidget(trend, 1, 0, 1, 4)
        system, info = panel()
        info.addWidget(label('这台电脑', 'section'))
        self.hardware = label('正在读取硬件信息…')
        self.hardware.setWordWrap(True)
        self.hardware.setStyleSheet('line-height: 1.5; font-size: 12px;')
        info.addWidget(self.hardware, 1)
        info.addWidget(button('仅保留桌面小组件', self.widget_only, 'small'))
        grid.addWidget(system, 1, 4, 1, 2)
        self.io_labels = {}
        for key, column, title in [('disk', 0, '磁盘活动'), ('network', 3, '网络活动')]:
            card, content = panel()
            top = QHBoxLayout()
            t = label(title, 'section')
            t.setStyleSheet(f'color: {COLORS[key]};')
            top.addWidget(t)
            top.addStretch()
            top.addWidget(button('查看详情', lambda checked=False, k=key: self.navigate(k), 'small'))
            content.addLayout(top)
            value = label('—')
            value.setStyleSheet('font-size: 19px; font-weight: 500;')
            content.addWidget(value)
            detail = label('等待采样', 'muted')
            detail.setWordWrap(True)
            content.addWidget(detail)
            self.io_labels[key] = value, detail
            grid.addWidget(card, 2, column, 1, 3)
        grid.setRowStretch(1, 1)
        for col in range(6):
            grid.setColumnStretch(col, 1)
        page.setMinimumHeight(650)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.add_page('overview', scroll)

    def build_processes(self):
        page, content = panel()
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索进程名称、PID或用户…')
        self.search.setClearButtonEnabled(True)
        bar.addWidget(self.search, 1)
        self.process_count = label('—', 'muted')
        bar.addWidget(self.process_count)
        content.addLayout(bar)
        self.process_model = ProcessModel()
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.process_model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.search.textChanged.connect(self.filter_processes)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(43)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 78)
        self.table.setColumnWidth(2, 125)
        self.table.setColumnWidth(3, 116)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 100)
        content.addWidget(self.table, 1)
        note = label('点击列标题排序。CPU以整机为100%，内存显示进程的常驻内存（RSS）。', 'muted')
        note.setWordWrap(True)
        content.addWidget(note)
        self.add_page('processes', page)

    def build_resource(self, key):
        page = QWidget()
        page.setObjectName('page')
        content = QVBoxLayout(page)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(16)
        graph, area = panel()
        self.resource_details[key] = label('等待采样', 'section')
        self.resource_details[key].setWordWrap(True)
        area.addWidget(self.resource_details[key])
        keys = {'disk': ['read', 'write'], 'network': ['down', 'up']}.get(key, [key])
        colors = [COLORS[key], '#e0a6c7'] if len(keys) == 2 else [COLORS[key]]
        if len(keys) == 2:
            legend = QHBoxLayout()
            for text, color in zip(('读取', '写入') if key == 'disk' else ('下载', '上传'), colors):
                l = label('● '+text)
                l.setStyleSheet(f'color: {color};')
                legend.addWidget(l)
            legend.addStretch()
            area.addLayout(legend)
        chart = Chart(keys, colors, self.history, percent=key not in ('disk', 'network'))
        self.resource_charts[key] = chart
        area.addWidget(chart, 1)
        content.addWidget(graph, 3)
        if key == 'cpu':
            cores, core_layout = panel()
            core_layout.addWidget(label('每个逻辑核心的实时利用率', 'section'))
            core_layout.addWidget(label('CPU编号与操作系统一致，每格独立使用0–100%刻度。', 'muted'))
            self.cpu_grid = CoreGrid()
            core_layout.addWidget(self.cpu_grid)
            content.addWidget(cores)
        if key == 'gpu':
            gauges, gauge_layout = panel()
            row = QHBoxLayout()
            self.gpu_gauge = UsageGauge(COLORS['gpu'], 110)
            row.addWidget(self.gpu_gauge)
            values = QVBoxLayout()
            values.addWidget(label('GPU 0实时利用率', 'section'))
            values.addWidget(label('圆环表示计算利用率，进度条表示显存占用。', 'muted'))
            self.vram_bar = QProgressBar()
            self.vram_bar.setRange(0, 1000)
            self.vram_bar.setFixedHeight(26)
            self.vram_bar.setStyleSheet('QProgressBar {background:#20354c; border:none; border-radius:6px; text-align:center;} QProgressBar::chunk {background:#367e72; border-radius:6px;}')
            values.addWidget(self.vram_bar)
            row.addLayout(values, 1)
            gauge_layout.addLayout(row)
            content.addWidget(gauges)
        detail_panel, detail_layout = panel()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.resource_body = getattr(self, 'resource_body', {})
        self.resource_body[key] = label('正在读取…')
        self.resource_body[key].setWordWrap(True)
        self.resource_body[key].setAlignment(Qt.AlignmentFlag.AlignTop)
        self.resource_body[key].setTextFormat(Qt.TextFormat.PlainText)
        self.resource_body[key].setStyleSheet('font-size: 14px; background: #172538; padding: 6px;')
        scroll.setWidget(self.resource_body[key])
        detail_layout.addWidget(scroll)
        content.addWidget(detail_panel, 2)
        if key in ('cpu', 'gpu'):
            page.setMinimumHeight(750 if key == 'cpu' else 690)
            wrapper = QScrollArea()
            wrapper.setWidgetResizable(True)
            wrapper.setWidget(page)
            self.add_page(key, wrapper)
        else:
            self.add_page(key, page)

    def build_settings(self):
        page = QWidget()
        page.setObjectName('page')
        content = QVBoxLayout(page)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(16)
        sampling, s = panel()
        s.addWidget(label('采样与显示', 'section'))
        row = QHBoxLayout()
        row.addWidget(label('刷新间隔'))
        row.addStretch()
        self.interval_combo = QComboBox()
        for value in (1, 2, 5):
            self.interval_combo.addItem(f'{value}秒', value)
        current = self.settings.value('interval', 1, int)
        self.interval_combo.setCurrentIndex(max(0, self.interval_combo.findData(current)))
        self.interval_combo.currentIndexChanged.connect(self.change_interval)
        row.addWidget(self.interval_combo)
        s.addLayout(row)
        s.addWidget(label('曲线保留最近5分钟。暂停显示时，小组件继续实时更新。', 'muted'))
        content.addWidget(sampling)
        widget, w = panel()
        w.addWidget(label('桌面小组件', 'section'))
        self.widget_check = QCheckBox('显示桌面小组件')
        self.widget_check.toggled.connect(self.toggle_widget)
        w.addWidget(self.widget_check)
        modes = QHBoxLayout()
        modes.addWidget(label('显示方式'))
        modes.addStretch()
        self.mode_combo = QComboBox()
        for title, value in [('桌面下层（位于应用下方）', 'desktop'), ('悬浮置顶（位于应用上方）', 'top'), ('普通悬浮窗口', 'normal')]:
            self.mode_combo.addItem(title, value)
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(self.settings.value('widget_mode', 'normal'))))
        self.mode_combo.currentIndexChanged.connect(lambda: self.set_widget_mode(self.mode_combo.currentData()))
        modes.addWidget(self.mode_combo)
        w.addLayout(modes)
        opacity = QHBoxLayout()
        opacity.addWidget(label('小组件不透明度'))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(60, 100)
        self.opacity_slider.setValue(self.settings.value('widget_opacity', 95, int))
        self.opacity_text = label(f'{self.opacity_slider.value()}%')
        self.opacity_slider.valueChanged.connect(self.change_opacity)
        opacity.addWidget(self.opacity_slider, 1)
        opacity.addWidget(self.opacity_text)
        w.addLayout(opacity)
        w.addWidget(label('拖动小组件顶部移动位置；右上角菜单可打开主窗口或退出。', 'muted'))
        content.addWidget(widget)
        startup, start = panel()
        start.addWidget(label('启动', 'section'))
        self.autostart = QCheckBox('登录后自动启动后台监控与顶栏')
        config_home = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))
        self.autostart_path = config_home/'autostart/pulse-monitor.desktop'
        self.service_path = config_home/'systemd/user/pulse-monitor.service'
        enabled = subprocess.run(['systemctl', '--user', 'is-enabled', 'pulse-monitor.service'], capture_output=True).returncode == 0 if self.service_path.exists() else self.autostart_path.exists()
        self.autostart.setChecked(enabled)
        self.autostart.toggled.connect(self.change_autostart)
        start.addWidget(self.autostart)
        self.settings_notice = label('关闭窗口后，后台采集与顶栏继续运行。从顶栏菜单重新打开窗口；选择“退出Pulse监控”停止后台。', 'muted')
        self.settings_notice.setWordWrap(True)
        start.addWidget(self.settings_notice)
        content.addWidget(startup)
        content.addStretch()
        self.add_page('settings', page)

    def build_panel_settings(self):
        page = QWidget()
        page.setObjectName('page')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        config = read_panel(self.settings)
        appearance, form = panel()
        form.addWidget(label('位置与样式', 'section'))
        self.panel_position = QComboBox()
        for text, value in [('左侧', 'left'), ('中间', 'center'), ('右侧', 'right')]:
            self.panel_position.addItem(text, value)
        self.panel_position.setCurrentIndex(self.panel_position.findData(config['position']))
        self.panel_style = QComboBox()
        for text, value in [('趋势图与数字', 'graphs'), ('负载条与数字', 'bars'), ('纯数字', 'numbers')]:
            self.panel_style.addItem(text, value)
        self.panel_style.setCurrentIndex(self.panel_style.findData(config['style']))
        for title, control in [('顶栏位置', self.panel_position), ('显示样式', self.panel_style)]:
            row = QHBoxLayout()
            row.addWidget(label(title))
            row.addStretch()
            row.addWidget(control)
            form.addLayout(row)
            control.currentIndexChanged.connect(self.save_panel_settings)
        self.panel_color = QCheckBox('使用资源配色（CPU蓝、内存紫、GPU青绿）')
        self.panel_color.setChecked(config['color'])
        self.panel_color.toggled.connect(self.save_panel_settings)
        form.addWidget(self.panel_color)
        width_row = QHBoxLayout()
        width_row.addWidget(label('单个图形宽度'))
        self.panel_width = QSlider(Qt.Orientation.Horizontal)
        self.panel_width.setRange(30, 90)
        self.panel_width.setValue(config['width'])
        self.panel_width_label = label(f"{config['width']}px")
        self.panel_width.valueChanged.connect(self.save_panel_settings)
        width_row.addWidget(self.panel_width, 1)
        width_row.addWidget(self.panel_width_label)
        form.addLayout(width_row)
        layout.addWidget(appearance)
        fields, content = panel()
        content.addWidget(label('显示项目', 'section'))
        grid = QGridLayout()
        self.panel_fields = {}
        for i, (key, title) in enumerate(FIELDS):
            checkbox = QCheckBox(title)
            checkbox.setChecked(config['fields'][key])
            checkbox.toggled.connect(self.save_panel_settings)
            self.panel_fields[key] = checkbox
            grid.addWidget(checkbox, i//3, i%3)
        content.addLayout(grid)
        note = label('趋势图显示最近60秒；负载条样式用独立小柱表示每个CPU逻辑核心，GPU和内存显示占用条。全部取消时保留菜单入口。K/M表示KiB/s、MiB/s。', 'muted')
        note.setWordWrap(True)
        content.addWidget(note)
        layout.addWidget(fields)
        preview, preview_layout = panel()
        preview_layout.addWidget(label('当前配置', 'section'))
        self.panel_preview = label()
        self.panel_preview.setWordWrap(True)
        preview_layout.addWidget(self.panel_preview)
        preview_layout.addWidget(label('修改自动保存，顶栏会在下一次采样时应用。仅移动Pulse，其他托盘图标保持原位。', 'muted'))
        layout.addWidget(preview)
        layout.addStretch()
        self.add_page('panel', page)
        self.update_panel_preview()

    def update_panel_preview(self):
        config = read_panel(self.settings)
        names = [title for key, title in FIELDS if config['fields'][key]]
        self.panel_preview.setText(f"{self.panel_position.currentText()} · {self.panel_style.currentText()}\n"+'、'.join(names or ['仅显示Pulse菜单']))

    def save_panel_settings(self):
        if not hasattr(self, 'panel_fields'):
            return
        self.settings.setValue('panel_position', self.panel_position.currentData())
        self.settings.setValue('panel_style', self.panel_style.currentData())
        self.settings.setValue('panel_color', self.panel_color.isChecked())
        self.settings.setValue('panel_width', self.panel_width.value())
        for key, checkbox in self.panel_fields.items():
            self.settings.setValue('panel_show_'+key, checkbox.isChecked())
        self.settings.sync()
        self.panel_width_label.setText(f'{self.panel_width.value()}px')
        self.update_panel_preview()

    def navigate(self, key):
        self.current_page = key
        self.stack.setCurrentWidget(self.pages[key])
        for name, b in self.nav.items():
            b.setChecked(name == key)
        self.heading.setText({'overview': '系统总览', 'processes': '进程', 'settings': '设置与小组件', 'panel': '顶栏设置'}.get(key, TITLES.get(key, '')+'详情'))
        self.subtitle.setText({
            'overview': 'CPU、显存与网络活动，一眼掌握。',
            'processes': '找到正在占用资源的进程。',
            'settings': '让监控适应你的工作习惯。',
            'panel': '选择你想随时看见的指标，调整位置与呈现方式。',
            'cpu': '整体负载、逻辑核心与处理器温度。',
            'memory': '物理内存、可用容量与交换空间。',
            'gpu': '显卡负载、显存、温度与功耗。',
            'disk': '整机物理磁盘吞吐与各挂载点容量。',
            'network': '活动物理网卡总速率与各接口流量。',
        }[key])
        display = self.paused_snapshot if self.paused else self.snapshot
        if display:
            self.render_snapshot(display)
            if self.paused:
                self.live.setText('Ⅱ  显示已暂停')

    def receive(self, s):
        self.snapshot = s
        self.history.append(dict(time=s['time'], cpu=s['cpu'], memory=s['memory']['percent'], gpu=gpu_usage(s),
                                 read=s['disk']['read'], write=s['disk']['write'], down=s['network']['down'], up=s['network']['up']))
        while self.history and s['time']-self.history[0]['time'] > 300:
            self.history.popleft()
        if self.widget.isVisible():
            self.widget.refresh(s)
        if self.isVisible() and not self.paused:
            self.render_snapshot(s)

    def render_snapshot(self, s):
        if self.current_page == 'overview':
            for metric in self.metrics.values():
                metric.refresh(s)
            self.overview_chart.update()
            gpu_name = s['gpus'][0]['name'] if s['gpus'] else 'GPU采集不可用'
            self.hardware.setText(f"{s['cpu_name']}\n{s['physical']}核 / {s['cores']}线程\n\n{gpu_name}\n\n{byte_text(s['memory']['total'])}内存\n运行{duration(s['uptime'])}")
            self.io_labels['disk'][0].setText(f"读 {byte_text(s['disk']['read'], True)}    写 {byte_text(s['disk']['write'], True)}")
            mounts = s['disk']['mounts']
            root = next((m for m in mounts if m['path'] == '/'), mounts[0] if mounts else None)
            self.io_labels['disk'][1].setText(f"{root['path']}  已用{root['percent']:.0f}%   剩余{byte_text(root['free'])}" if root else '未发现可读取的挂载点')
            self.io_labels['network'][0].setText(f"↓ {byte_text(s['network']['down'], True)}    ↑ {byte_text(s['network']['up'], True)}")
            self.io_labels['network'][1].setText(s['network']['names'])
        elif self.current_page == 'processes':
            self.update_processes(s['processes'])
        elif self.current_page in TITLES:
            self.render_resource(self.current_page, s)
        stamp = datetime.fromtimestamp(s['wall_time']).strftime('%H:%M:%S')
        self.status.setText(f"{s['hostname']}   更新于{stamp}   {len(s['processes'])}个可读取进程")
        self.live.setText('●  实时更新')

    def render_resource(self, key, s):
        m = s['memory']
        if key == 'cpu':
            self.cpu_grid.set_values(s['cpus'])
            freq = f"{s['frequency']/1000:.2f} GHz" if s['frequency'] else '暂无读数'
            heading = f"{s['cpu']:.1f}%使用率     {temperature(s['temperature'])}     {freq}"
            body = f"{s['cpu_name']}\n{s['physical']}个物理核心，{s['cores']}个逻辑核心\n平均负载（1 / 5 / 15分钟）："+' / '.join(f'{v:.2f}' for v in s['load'])
        elif key == 'memory':
            heading = f"{m['percent']:.1f}%使用率     {byte_text(m['used'])} / {byte_text(m['total'])}"
            body = f"物理内存总量    {byte_text(m['total'])}\n\n已用（总量减可用）    {byte_text(m['used'])}\n\n可用    {byte_text(m['available'])}\n\n文件缓存    {byte_text(m['cached'])}\n\n交换空间    {byte_text(s['swap']['used'])} / {byte_text(s['swap']['total'])}\n\n可用内存包括可以回收的缓存；文件缓存单独列出，不与已用量直接相加。"
        elif key == 'gpu':
            usage = gpu_usage(s)
            self.gpu_gauge.set_value(usage)
            gpu = s['gpus'][0] if s['gpus'] else None
            if gpu and gpu['used'] is not None and gpu['total']:
                self.vram_bar.setValue(round(gpu['used']/gpu['total']*1000))
                self.vram_bar.setFormat(f"显存 {gpu['used']/1024:.1f} / {gpu['total']/1024:.1f} GiB（{gpu['used']/gpu['total']*100:.1f}%）")
            else:
                self.vram_bar.setValue(0)
                self.vram_bar.setFormat('显存暂无读数')
            heading = f'{usage:.0f}%使用率' if usage is not None else 'GPU暂无利用率读数'
            cards = []
            for i, gpu in enumerate(s['gpus']):
                used = byte_text(gpu['used']*1024**2) if gpu['used'] is not None else '暂无读数'
                total = byte_text(gpu['total']*1024**2) if gpu['total'] is not None else '暂无读数'
                power = f"{gpu['power']:.1f} W" if gpu['power'] is not None else '暂无读数'
                load = f"{gpu['usage']:.0f}%" if gpu['usage'] is not None else '暂无读数'
                cards.append(f"GPU {i}    {gpu['name']}\n\n利用率    {load}       温度    {temperature(gpu['temperature'])}\n\n显存    {used} / {total}       功耗    {power}")
            body = '\n\n'.join(cards) if cards else s['gpu_error']
            if len(cards) > 1:
                body += '\n\n趋势图与小组件显示GPU 0。'
        elif key == 'disk':
            heading = f"读取 {byte_text(s['disk']['read'], True)}     写入 {byte_text(s['disk']['write'], True)}"
            body = '\n\n'.join(f"{d['path']}    {d['device']}\n已用{d['percent']:.1f}%    {byte_text(d['used'])} / {byte_text(d['total'])}    剩余{byte_text(d['free'])}" for d in s['disk']['mounts']) or '未发现可读取的挂载点。'
        else:
            heading = f"↓ {byte_text(s['network']['down'], True)}     ↑ {byte_text(s['network']['up'], True)}"
            body = f"趋势图统计：{s['network']['names']}\n\n"+'\n\n'.join(
                f"{i['name']}    {'已连接' if i['up'] else '未连接'}    {i['ip']}\n↓ {byte_text(i['down'], True)}    ↑ {byte_text(i['up_rate'], True)}    累计接收{byte_text(i['received'])} / 发送{byte_text(i['sent'])}"
                for i in s['network']['interfaces'] if i['name'] != 'lo')
        self.resource_details[key].setText(heading)
        self.resource_body[key].setText(body)
        self.resource_charts[key].update()

    def update_processes(self, rows):
        selected = self.table.currentIndex()
        pid = self.proxy.index(selected.row(), 1).data(Qt.ItemDataRole.UserRole) if selected.isValid() else None
        scroll = self.table.verticalScrollBar().value()
        self.process_model.replace(rows)
        if pid is not None:
            for i, row in enumerate(rows):
                if row['pid'] == pid:
                    target = self.proxy.mapFromSource(self.process_model.index(i, 0))
                    if target.isValid():
                        self.table.setCurrentIndex(target)
                    break
        self.table.verticalScrollBar().setValue(scroll)
        self.update_process_count()

    def update_process_count(self):
        self.process_count.setText(f'{self.proxy.rowCount()} / {self.process_model.rowCount()}个进程')

    def filter_processes(self, text):
        self.proxy.setFilterFixedString(text)
        self.update_process_count()

    def focus_search(self):
        self.navigate('processes')
        self.search.setFocus()

    def toggle_pause(self):
        self.paused = not self.paused
        self.paused_snapshot = self.snapshot
        charts = [self.overview_chart, *self.resource_charts.values(), *(m.chart for m in self.metrics.values())]
        for chart in charts:
            chart.history = deque(self.history) if self.paused else self.history
        self.pause_button.setText('继续显示' if self.paused else '暂停显示')
        self.live.setText('Ⅱ  显示已暂停' if self.paused else '●  实时更新')
        if not self.paused and self.snapshot:
            self.render_snapshot(self.snapshot)

    def change_range(self):
        seconds = self.range_combo.currentData()
        for chart in [self.overview_chart, *self.resource_charts.values()]:
            chart.seconds = seconds
            chart.update()

    def change_interval(self):
        seconds = self.interval_combo.currentData()
        self.settings.setValue('interval', seconds)
        self.interval_changed.emit(float(seconds))

    def toggle_widget(self, visible):
        if not hasattr(self, 'widget'):
            return
        self.settings.setValue('widget_visible', visible)
        self.widget.setVisible(visible)
        if visible and self.settings.value('widget_mode', 'normal') != 'desktop':
            self.widget.raise_()
            self.widget.activateWindow()
        self.widget_check.blockSignals(True)
        self.widget_check.setChecked(visible)
        self.widget_check.blockSignals(False)
        self.widget_button.setText('隐藏小组件' if visible else '桌面小组件')
        if visible and self.snapshot:
            self.widget.refresh(self.snapshot)

    def set_widget_mode(self, mode):
        self.settings.setValue('widget_mode', mode)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(mode))
        self.mode_combo.blockSignals(False)
        self.widget.apply_mode()

    def change_opacity(self, value):
        self.settings.setValue('widget_opacity', value)
        self.opacity_text.setText(f'{value}%')
        self.widget.setWindowOpacity(value/100)

    def change_autostart(self, enabled):
        try:
            if self.service_path.exists():
                result = subprocess.run(['systemctl', '--user', 'enable' if enabled else 'disable', 'pulse-monitor.service'], capture_output=True, text=True)
                if result.returncode:
                    self.settings_notice.setText('自启动设置失败：'+result.stderr.strip())
                    self.autostart.blockSignals(True)
                    self.autostart.setChecked(not enabled)
                    self.autostart.blockSignals(False)
                else:
                    self.settings_notice.setText('登录自启动已开启。' if enabled else '登录自启动已关闭，当前后台继续运行。')
                return
            if enabled:
                self.autostart_path.parent.mkdir(parents=True, exist_ok=True)
                self.autostart_path.write_text(desktop_entry(widget=True))
            else:
                self.autostart_path.unlink(missing_ok=True)
        except OSError as error:
            self.settings_notice.setText(f'自启动设置保存失败：{error}')
            self.autostart.blockSignals(True)
            self.autostart.setChecked(self.autostart_path.exists())
            self.autostart.blockSignals(False)

    def widget_only(self):
        self.toggle_widget(True)
        self.hide()

    def show_main(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if self.snapshot and not self.paused:
            self.render_snapshot(self.snapshot)

    def closeEvent(self, event):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('widget_pos', self.widget.pos())
        self.hide()
        event.accept()
