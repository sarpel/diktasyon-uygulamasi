"""Başlıklı, kopyala düğmeli metin paneli; ham/düzeltilmiş farkını git diff gibi (silinen
kırmızı, eklenen yeşil) vurgular ve ipucunda gösterir."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
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
from dikte.platform.clipboard import copy_text
from dikte.ui.icons import copy_icon

# GitHub'ın fark renkleri, yarı saydam: açık ve koyu sistem temasında okunaklı kalır.
ADDED_COLOR = QColor(46, 160, 67, 110)
REMOVED_COLOR = QColor(248, 81, 73, 110)


class TextPane(QWidget):
    """Düzenlenebilir metin kutusu + kopyala düğmesi; kopyalanınca `copied(metin)` yayar.

    Vurgulanan değişikliğin üzerine gelince "‘eski’ → ‘yeni’ (neden)" ipucu gösterilir."""

    copied = Signal(str)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.exclude_history = True  # Windows pano geçmişinden dışla (ayar; pencere günceller)
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
        self._side = "new"
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

    def _span(self, c: Change) -> tuple[int, int]:
        return (c.orig_start, c.orig_end) if self._side == "old" else (c.start, c.end)

    def set_highlights(self, changes: Sequence[Change], *, side: str = "new") -> None:
        """Değişiklikleri git diff gibi vurgular; öncekilerin yerini alır.

        `side="new"` (düzeltilmiş metin): eklenen/yeni hâli yeşil. `side="old"` (ham metin):
        silinen/değişen kelimeler kırmızı. Bu panelde aralığı olmayan (ör. düzeltilmişte
        saf silme) ya da konumu bilinmeyen (eski kayıt) değişiklikler atlanır."""
        self._side = side
        length = len(self.editor.toPlainText())
        self._changes = tuple(
            c for c in changes if 0 <= self._span(c)[0] < self._span(c)[1] <= length
        )
        color = REMOVED_COLOR if side == "old" else ADDED_COLOR
        selections = []
        for c in self._changes:
            start, end = self._span(c)
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format.setBackground(color)
            selections.append(sel)
        self.editor.setExtraSelections(selections)

    def _change_at(self, offset: int) -> Change | None:
        for c in self._changes:
            start, end = self._span(c)
            if start <= offset < end:
                return c
        return None

    def eventFilter(self, obj, event):
        if obj is self.editor.viewport() and event.type() == QEvent.Type.ToolTip:
            offset = self.editor.cursorForPosition(event.pos()).position()
            c = self._change_at(offset)
            if c is not None:
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
        copy_text(text, exclude_history=self.exclude_history)
        self.copied.emit(text)
