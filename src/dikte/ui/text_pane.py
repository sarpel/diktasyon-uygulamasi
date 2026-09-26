"""Başlıklı, kopyala düğmeli metin paneli; LLM değişikliklerini vurgular ve ipucunda gösterir."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QTextEdit,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from dikte.llm.diff import Change
from dikte.ui.icons import copy_icon

HIGHLIGHT_COLOR = QColor(255, 235, 59, 90)


class TextPane(QWidget):
    """Düzenlenebilir metin kutusu + kopyala düğmesi; kopyalanınca `copied(metin)` yayar.

    Vurgulanan değişikliğin üzerine gelince "‘eski’ → ‘yeni’ (neden)" ipucu gösterilir."""

    copied = Signal(str)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight:600;")
        self.copy_btn = QToolButton()
        self.copy_btn.setIcon(copy_icon())
        self.copy_btn.setToolTip("Kopyala (Ctrl+Shift+C)")
        self.copy_btn.setAutoRaise(True)
        self.copy_btn.clicked.connect(self.copy)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("…")
        self.editor.setMouseTracking(True)
        self.editor.viewport().installEventFilter(self)
        self._changes: tuple[Change, ...] = ()
        header = QHBoxLayout()
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.copy_btn, alignment=Qt.AlignmentFlag.AlignRight)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(header)
        lay.addWidget(self.editor, 1)

    def set_text(self, text: str) -> None:
        """Metni değiştirir (aynıysa imleç korunur) ve vurguları temizler."""
        if self.editor.toPlainText() != text:
            self.editor.setPlainText(text)
        self.set_highlights(())

    def set_highlights(self, changes: Sequence[Change]) -> None:
        """Konumu geçerli değişiklikleri sarıyla vurgular; öncekilerin yerini alır."""
        self._changes = tuple(c for c in changes if c.start >= 0 and c.end > c.start)
        selections = []
        for c in self._changes:
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(c.start)
            cursor.setPosition(c.end, QTextCursor.MoveMode.KeepAnchor)
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format.setBackground(HIGHLIGHT_COLOR)
            selections.append(sel)
        self.editor.setExtraSelections(selections)

    def eventFilter(self, obj, event):
        if obj is self.editor.viewport() and event.type() == QEvent.Type.ToolTip:
            offset = self.editor.cursorForPosition(event.pos()).position()
            for c in self._changes:
                if c.start <= offset < c.end:
                    QToolTip.showText(
                        event.globalPos(),
                        f"‘{c.original}’ → ‘{c.replacement}’ ({c.reason})",
                        self.editor,
                    )
                    return True
            QToolTip.hideText()
            return True
        return super().eventFilter(obj, event)

    def text(self) -> str:
        return self.editor.toPlainText()

    def set_busy(self, busy: bool) -> None:
        self.copy_btn.setEnabled(not busy)
        self.editor.setPlaceholderText("Bekleniyor…" if busy else "…")

    def copy(self) -> None:
        """Metni panoya yazar ve `copied` yayar; boşsa hiçbir şey yapmaz."""
        text = self.text()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.copied.emit(text)
