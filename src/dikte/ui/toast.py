from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QWidget


class Toast(QLabel):
    def __init__(self, parent: QWidget, text: str, ms: int = 1500):
        super().__init__(text, parent)
        self.setStyleSheet(
            "background:rgba(30,30,30,220);color:white;padding:8px 14px;border-radius:8px;"
        )
        self.adjustSize()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 24)
        self.show()
        self.raise_()
        QTimer.singleShot(ms, self.deleteLater)

    @staticmethod
    def show_message(parent: QWidget, text: str) -> "Toast":
        return Toast(parent, text)
