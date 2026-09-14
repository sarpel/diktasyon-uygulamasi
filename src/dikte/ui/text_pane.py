from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dikte.ui.icons import copy_icon


class TextPane(QWidget):
    copied = Signal(str)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight:600;")
        self.copy_btn = QToolButton()
        self.copy_btn.setIcon(copy_icon())
        self.copy_btn.setToolTip("Kopyala (Ctrl+Shift+C)")
        self.copy_btn.setAutoRaise(True)
        self.copy_btn.clicked.connect(self._copy)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("…")
        header = QHBoxLayout()
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.copy_btn, alignment=Qt.AlignRight)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(header)
        lay.addWidget(self.editor, 1)

    def set_text(self, text: str) -> None:
        if self.editor.toPlainText() != text:
            self.editor.setPlainText(text)

    def text(self) -> str:
        return self.editor.toPlainText()

    def set_busy(self, busy: bool) -> None:
        self.copy_btn.setEnabled(not busy)
        self.editor.setPlaceholderText("Bekleniyor…" if busy else "…")

    def _copy(self) -> None:
        text = self.text()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.copied.emit(text)
