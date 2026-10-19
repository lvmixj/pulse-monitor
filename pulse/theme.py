"""Appearance only: immutable semantic palettes and one shared Qt stylesheet.

A theme may set colors and repaint. It has no access to monitor state,
settings, navigation, visibility, sampling, or signal connections.
"""
from types import MappingProxyType
from PySide6.QtWidgets import QApplication

THEMES = MappingProxyType({'ocean': '深海蓝', 'light': '浅色', 'graphite': '石墨黑'})
COLORS = MappingProxyType({key: key for key in ('cpu', 'memory', 'gpu', 'disk', 'network')})

# Every theme implements the same named roles. Layout and type live in shared QSS.
PALETTES = MappingProxyType({name: MappingProxyType(values) for name, values in {
    'ocean': dict(canvas='#101b2b', surface='#172538', sidebar='#132032', text='#e6edf7',
                  muted='#a2b3c8', border='#344961', control='#21334a', hover='#2b425e',
                  pressed='#365171', accent='#90cbff', primary='#2c70aa', on_primary='#ffffff',
                  selection='#263e58', grid='#344961', track='#30465f',
                  cpu='#62b5ff', memory='#bc9bff', gpu='#59d9be', disk='#ffc17b',
                  network='#70d1ed', secondary='#e0a6c7', success='#59d9be', warning='#ffc17b'),
    'light': dict(canvas='#f3f5f8', surface='#ffffff', sidebar='#e9eef5', text='#192b40',
                  muted='#53667d', border='#b9c9db', control='#e7edf5', hover='#dbe6f2',
                  pressed='#cbdced', accent='#185e98', primary='#266da8', on_primary='#ffffff',
                  selection='#d4e5f6', grid='#d4deea', track='#dce5ef',
                  cpu='#216da9', memory='#7952b5', gpu='#087c65', disk='#a35d0d',
                  network='#187893', secondary='#a7497d', success='#087c65', warning='#94540a'),
    'graphite': dict(canvas='#181a1e', surface='#22252b', sidebar='#1d2025', text='#eceef2',
                     muted='#adb3bf', border='#4a5260', control='#30353e', hover='#3c4350',
                     pressed='#495363', accent='#a8c9f1', primary='#416b9f', on_primary='#ffffff',
                     selection='#35465e', grid='#414954', track='#444f60',
                     cpu='#83b7ef', memory='#c3a5ed', gpu='#77cdb7', disk='#e7b47e',
                     network='#88c7df', secondary='#dba6c1', success='#77cdb7', warning='#e7b47e'),
}.items()})

_QSS = '''
QWidget { color: $text; font-family: "Noto Sans CJK SC"; font-size: 13px; }
QMainWindow, QDialog, QWidget#page, QWidget#workspace { background: $canvas; }
QFrame#sidebar { background: $sidebar; border-right: 1px solid $border; }
QFrame#panel, QFrame#metric { background: $surface; border: 1px solid $border; border-radius: 10px; }
QFrame#metric:hover { border-color: $accent; }
QLabel { background: transparent; border: none; }
QLabel#muted, QLabel#eyebrow { color: $muted; }
QLabel#eyebrow { font-size: 12px; }
QLabel#title { font-size: 25px; font-weight: 600; }
QLabel#brand { font-size: 27px; font-weight: 600; color: $accent; }
QLabel#widgetBrand { font-size: 17px; font-weight: 600; color: $accent; }
QLabel#section { font-size: 15px; font-weight: 600; }
QLabel#value { font-size: 32px; font-weight: 600; }
QLabel#widgetValue { font-size: 24px; font-weight: 600; }
QLabel#ioValue { font-size: 19px; font-weight: 500; }
QLabel#resourceValue { font-size: 21px; font-weight: 600; }
QLabel#resourceBody { font-size: 14px; background: $surface; padding: 4px; }
QPushButton { background: $control; border: 1px solid $border; border-radius: 6px; padding: 8px 12px; }
QPushButton:hover { background: $hover; border-color: $accent; }
QPushButton:pressed { background: $pressed; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus { border: 1px solid $accent; }
QPushButton:disabled { color: $muted; background: $surface; }
QPushButton#primary { background: $primary; border-color: $primary; color: $on_primary; }
QPushButton#primary:hover { background: $pressed; color: $text; }
QPushButton#nav { text-align: left; background: transparent; border: 1px solid transparent; padding: 10px 12px; }
QPushButton#nav:hover { background: $control; }
QPushButton#nav:checked { background: $selection; border-color: $border; color: $accent; font-weight: 600; }
QPushButton#small { padding: 5px 10px; }
QLineEdit, QComboBox { background: $surface; border: 1px solid $border; border-radius: 6px; padding: 8px 12px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: $surface; color: $text; selection-background-color: $selection; selection-color: $text; padding: 6px; }
QTableView { background: $surface; alternate-background-color: $canvas; border: none; gridline-color: $border; selection-background-color: $selection; selection-color: $text; }
QTableView::item { padding: 8px; border: none; }
QHeaderView::section { background: $control; color: $muted; border: none; border-bottom: 1px solid $border; padding: 10px; }
QScrollArea, QScrollArea > QWidget > QWidget { border: none; background: $canvas; }
QScrollBar:vertical { background: $canvas; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: $canvas; height: 8px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 4px; min-width: 32px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid $muted; border-radius: 4px; background: $surface; }
QCheckBox::indicator:checked { background: $primary; border-color: $accent; }
QCheckBox:focus { color: $accent; }
QSlider::groove:horizontal { height: 5px; background: $track; border-radius: 2px; }
QSlider::handle:horizontal { width: 16px; margin: -6px 0; background: $accent; border-radius: 8px; }
QProgressBar { background: $track; border: none; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: $gpu; border-radius: 5px; }
QMenu { background: $surface; border: 1px solid $border; padding: 6px; }
QMenu::item { padding: 8px 18px; border-radius: 4px; }
QMenu::item:selected { background: $selection; }
QToolTip { background: $surface; color: $text; border: 1px solid $border; padding: 6px; }
'''


def stylesheet(name):
    from string import Template
    palette = PALETTES[name]
    tones = '\n'.join(f'QLabel[tone="{role}"] {{color: {palette[role]};}}'
                      for role in ('cpu', 'memory', 'gpu', 'disk', 'network', 'secondary', 'success', 'warning'))
    return Template(_QSS).substitute(palette)+'\n'+tones


def color(role):
    app = QApplication.instance()
    name = app.property('pulseTheme') if app else None
    return PALETTES[name if name in THEMES else 'ocean'][role]


def apply_theme(app, name):
    """Update presentation only; the caller owns preference persistence."""
    name = name if name in THEMES else 'ocean'
    app.setProperty('pulseTheme', name)
    app.setStyleSheet(stylesheet(name))
    return name


STYLE = stylesheet('ocean')
