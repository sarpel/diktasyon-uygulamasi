from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

_COLORS = {"idle": QColor("#4A90E2"), "recording": QColor("#E53935"), "busy": QColor("#F5A623")}


def make_tray_icon(state: str = "idle", size: int = 64) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(_COLORS.get(state, _COLORS["idle"]))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(size * 0.1, size * 0.1, size * 0.8, size * 0.8))
    p.setPen(
        QPen(
            QColor("white"),
            size * 0.12,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
    )
    for i, h in enumerate((0.25, 0.5, 0.35)):
        x = size * (0.35 + i * 0.15)
        p.drawLine(int(x), int(size * (0.5 - h / 2)), int(x), int(size * (0.5 + h / 2)))
    p.end()
    return QIcon(pm)


def copy_icon(size: int = 32) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    text_color = QApplication.palette().text().color()  # koyu/açık temaya uyum sağlar
    p.setPen(QPen(text_color, 2))
    p.drawRoundedRect(QRectF(size * 0.35, size * 0.35, size * 0.45, size * 0.5), 3, 3)
    p.drawRoundedRect(QRectF(size * 0.2, size * 0.15, size * 0.45, size * 0.5), 3, 3)
    p.end()
    return QIcon(pm)
