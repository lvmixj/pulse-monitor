BASE = '#101b2b'
SURFACE = '#172538'
TEXT = '#e6edf7'
MUTED = '#a2b3c8'
COLORS = {'cpu': '#62b5ff', 'memory': '#bc9bff', 'gpu': '#59d9be',
          'disk': '#ffc17b', 'network': '#70d1ed'}

STYLE = '''
QWidget { color: #e6edf7; font-family: "Noto Sans CJK SC"; font-size: 13px; }
QMainWindow, QDialog, QWidget#page { background: #101b2b; }
QFrame#sidebar { background: #132032; border-right: 1px solid #26364b; }
QFrame#panel { background: #172538; border: 1px solid #293b50; border-radius: 16px; }
QFrame#metric { background: #172538; border: 1px solid #293b50; border-radius: 14px; }
QLabel { background: transparent; border: none; }
QLabel#muted { color: #a2b3c8; }
QLabel#title { font-size: 26px; font-weight: 600; }
QLabel#section { font-size: 16px; font-weight: 600; }
QLabel#value { font-size: 32px; font-weight: 600; }
QPushButton { background: #21334a; border: 1px solid #344961; border-radius: 8px; padding: 8px 14px; }
QPushButton:hover { background: #2b425e; border-color: #62b5ff; }
QPushButton:pressed { background: #365171; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus { border: 1px solid #80c4ff; }
QPushButton#primary { background: #357cb7; border-color: #5297ce; color: white; }
QPushButton#nav { text-align: left; background: transparent; border: 1px solid transparent; padding: 11px 15px; }
QPushButton#nav:hover { background: #21334a; }
QPushButton#nav:checked { background: #263e58; border-color: #3c5877; color: #90cbff; }
QPushButton#small { padding: 4px 9px; }
QLineEdit, QComboBox { background: #142133; border: 1px solid #344961; border-radius: 8px; padding: 8px 12px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #21334a; selection-background-color: #365171; padding: 6px; }
QTableView { background: #172538; alternate-background-color: #1a2a3e; border: none; gridline-color: #293b50; selection-background-color: #304a68; }
QTableView::item { padding: 8px; border: none; }
QHeaderView::section { background: #1c2d42; color: #a2b3c8; border: none; border-bottom: 1px solid #344961; padding: 10px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #142133; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #3b516b; border-radius: 4px; min-height: 32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #142133; height: 8px; }
QScrollBar::handle:horizontal { background: #3b516b; border-radius: 4px; min-width: 32px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #55708e; border-radius: 5px; background: #142133; }
QCheckBox::indicator:checked { background: #62b5ff; border-color: #92cbff; }
QSlider::groove:horizontal { height: 5px; background: #344961; border-radius: 2px; }
QSlider::handle:horizontal { width: 16px; margin: -6px 0; background: #90cbff; border-radius: 8px; }
QMenu { background: #21334a; border: 1px solid #3b516b; padding: 6px; }
QMenu::item { padding: 8px 18px; border-radius: 5px; }
QMenu::item:selected { background: #365171; }
QToolTip { background: #263e58; color: #e6edf7; border: 1px solid #55708e; padding: 6px; }
'''
