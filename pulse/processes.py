from PySide6.QtCore import QAbstractTableModel, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor
from .collector import byte_text
from .theme import color as theme_color


class ProcessSortProxy(QSortFilterProxyModel):
    def lessThan(self, left, right):
        if left.column() in (1, 2, 3):
            # Compare Python numbers directly: RSS values cross QVariant's
            # signed 32-bit boundary when a process uses more than 2 GiB.
            return left.data(Qt.ItemDataRole.UserRole) < right.data(Qt.ItemDataRole.UserRole)
        return super().lessThan(left, right)


class ProcessModel(QAbstractTableModel):
    columns = [('进程名称', 'name'), ('PID', 'pid'), ('CPU（整机）', 'cpu'),
               ('内存', 'memory'), ('用户', 'user'), ('状态', 'status')]

    def __init__(self):
        super().__init__()
        self.rows = []

    def rowCount(self, parent=None):
        return len(self.rows)

    def columnCount(self, parent=None):
        return len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.columns[section][0]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        key = self.columns[index.column()][1]
        value = self.rows[index.row()][key]
        if role == Qt.ItemDataRole.UserRole:
            return value
        if role == Qt.ItemDataRole.DisplayRole:
            if key == 'cpu':
                return f'{value:.1f}%'
            if key == 'memory':
                return byte_text(value)
            if key == 'status':
                return {'running': '运行中', 'sleeping': '休眠', 'idle': '空闲',
                        'stopped': '已停止', 'zombie': '僵尸', 'disk-sleep': '等待I/O'}.get(value, value)
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and key in ('cpu', 'memory', 'pid'):
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ForegroundRole and key == 'cpu' and value >= 10:
            return QColor(theme_color('cpu'))
        if role == Qt.ItemDataRole.ToolTipRole:
            return 'CPU按全部逻辑核心归一化，100%代表整机CPU满载。' if key == 'cpu' else str(value)

    def replace(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()
