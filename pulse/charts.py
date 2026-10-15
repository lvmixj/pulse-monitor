import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .theme import MUTED


class Chart(QWidget):
    """Time-aligned, unsmoothed traces; missing measurements leave a gap."""
    def __init__(self, keys, colors, history, percent=True, compact=False):
        super().__init__()
        self.keys, self.colors, self.history = keys, colors, history
        self.percent, self.compact = percent, compact
        self.seconds = 60
        self.setMinimumHeight(62 if compact else 170)
        self.setToolTip('曲线按真实采样时间绘制；启动前的时间与不可用数据保持空白。')

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = QRectF(1, 4, self.width()-2, self.height()-8) if self.compact else QRectF(43, 12, self.width()-58, self.height()-38)
        now = self.history[-1]['time'] if self.history else time.monotonic()
        samples = [s for s in self.history if s['time'] >= now-self.seconds]
        values = [s.get(k) for s in samples for k in self.keys if s.get(k) is not None]
        top = 100 if self.percent else max(1024, max(values, default=0)*1.2)
        if not self.compact:
            p.setFont(QFont('Noto Sans CJK SC', 8))
            p.setPen(QPen(QColor('#2c4057'), 1, Qt.PenStyle.DashLine))
            for fraction in (0, .25, .5, .75, 1):
                y = plot.bottom()-plot.height()*fraction
                p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(MUTED))
            for fraction in (0, .5, 1):
                value = top*fraction
                label = f'{value:.0f}%' if self.percent else self.rate_axis(value)
                p.drawText(QRectF(0, plot.bottom()-plot.height()*fraction-8, 38, 18), Qt.AlignmentFlag.AlignRight, label)
            p.drawText(QRectF(plot.left(), plot.bottom()+7, 100, 20), f'{self.seconds}秒前')
            p.drawText(QRectF(plot.right()-45, plot.bottom()+7, 45, 20), Qt.AlignmentFlag.AlignRight, '现在')
        for key, color in zip(self.keys, self.colors):
            runs, run = [], []
            for sample in samples:
                value = sample.get(key)
                if value is None:
                    if run:
                        runs.append(run)
                        run = []
                    continue
                x = plot.right()-(now-sample['time'])/self.seconds*plot.width()
                y = plot.bottom()-min(1, max(0, value/top))*plot.height()
                run.append(QPointF(x, y))
            if run:
                runs.append(run)
            for points in runs:
                path = QPainterPath(points[0])
                for point in points[1:]:
                    path.lineTo(point)
                fill = QPainterPath(path)
                fill.lineTo(points[-1].x(), plot.bottom())
                fill.lineTo(points[0].x(), plot.bottom())
                fill.closeSubpath()
                gradient = QLinearGradient(0, plot.top(), 0, plot.bottom())
                tint = QColor(color)
                tint.setAlpha(55)
                gradient.setColorAt(0, tint)
                tint.setAlpha(2)
                gradient.setColorAt(1, tint)
                p.fillPath(fill, gradient)
                p.setPen(QPen(QColor(color), 2))
                p.drawPath(path)
                p.setBrush(QColor(color))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(points[-1], 2.5, 2.5)
        p.end()

    @staticmethod
    def rate_axis(value):
        if value >= 1024**3:
            return f'{value/1024**3:.1f}G'
        if value >= 1024**2:
            return f'{value/1024**2:.1f}M'
        return f'{value/1024:.0f}K'


class UsageGauge(QWidget):
    def __init__(self, color, size=96):
        super().__init__()
        self.color, self.value = color, None
        self.setFixedSize(size, size)

    def set_value(self, value):
        self.value = value
        self.setToolTip('暂无利用率读数' if value is None else f'利用率{value:.1f}%')
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(7, 7, -7, -7)
        p.setPen(QPen(QColor('#30465f'), 7))
        p.drawEllipse(rect)
        if self.value is not None:
            p.setPen(QPen(QColor(self.color), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, 90*16, -round(max(0, min(100, self.value))*3.6*16))
        p.setPen(QColor('#e6edf7'))
        font = QFont('Noto Sans CJK SC', 15)
        font.setBold(True)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '—' if self.value is None else f'{self.value:.0f}%')


class CoreGrid(QWidget):
    """A fixed 0–100% scale for each logical processor, in OS index order."""
    def __init__(self, compact=False):
        super().__init__()
        self.compact = compact
        self.values = []
        self.setMouseTracking(True)

    def columns(self):
        return max(1, min(8, self.width()//(42 if self.compact else 100)))

    def set_values(self, values):
        self.values = list(values)
        self.adjust_height()
        self.update()

    def adjust_height(self):
        rows = (len(self.values)+self.columns()-1)//self.columns()
        self.setFixedHeight(max(1, rows)*(36 if self.compact else 56))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_height()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cols = self.columns()
        width = self.width()/cols
        height = 36 if self.compact else 56
        for i, value in enumerate(self.values):
            rect = QRectF((i%cols)*width+2, (i//cols)*height+2, width-5, height-5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor('#20354c'))
            p.drawRoundedRect(rect, 5, 5)
            p.setPen(QColor('#d3e5f8'))
            p.setFont(QFont('Noto Sans CJK SC', 7 if self.compact else 9))
            if self.compact:
                p.drawText(rect.adjusted(0, 0, 0, -9), Qt.AlignmentFlag.AlignCenter, f'{i}: {value:.0f}%')
            else:
                p.drawText(rect.adjusted(8, 3, -8, -20), Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter, f'CPU {i}')
                p.drawText(rect.adjusted(8, 3, -8, -20), Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter, f'{value:.0f}%')
            bar = rect.adjusted(6, rect.height()-10, -6, -5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor('#354b63'))
            p.drawRoundedRect(bar, 2, 2)
            p.setBrush(QColor('#ffc17b' if value >= 85 else '#62b5ff'))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width()*value/100, bar.height()), 2, 2)

    def mouseMoveEvent(self, event):
        cols = self.columns()
        row = int(event.position().y()//(36 if self.compact else 56))
        col = int(event.position().x()//(self.width()/cols))
        i = row*cols+col
        self.setToolTip(f'逻辑核心CPU {i}：{self.values[i]:.1f}%' if i < len(self.values) else '')
