from __future__ import annotations

import unicodedata

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dikte.core.state import Session

PREVIEW_CHARS = 80


_DOTLESS_I = str.maketrans({"ı": "i"})  # NFKD ayrıştırmaz; elle eşlenir


def normalize(text: str) -> str:
    """Aramayı büyük/küçük harf ve Türkçe aksanlardan bağımsız kılar.

    'İstanbul' → 'istanbul', 'toplantısı' → 'toplantisi'; böylece kullanıcı aksansız
    yazdığında da kayıtları bulabilir.
    """
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.translate(_DOTLESS_I)


class HistoryPanel(QDockWidget):
    """Geçmiş oturumlarını listeler; arama, yükleme, kopyalama ve silme sağlar."""

    session_selected = Signal(object)
    delete_requested = Signal(str)
    clear_requested = Signal()
    export_requested = Signal(str)

    def __init__(self, parent=None, dialog=None):
        super().__init__("Geçmiş", parent)
        self.setObjectName("historyDock")
        self._sessions: tuple[Session, ...] = ()
        self._dialog = dialog or QFileDialog.getSaveFileName

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Ara…")
        self.search_edit.setClearButtonEnabled(True)
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.empty_label = QLabel("Henüz kayıt yok.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.copy_btn = QPushButton("Kopyala")
        self.delete_btn = QPushButton("Sil")
        self.clear_btn = QPushButton("Tümünü temizle")
        self.export_btn = QPushButton("Dışa aktar…")

        buttons = QHBoxLayout()
        for b in (self.copy_btn, self.delete_btn, self.clear_btn, self.export_btn):
            buttons.addWidget(b)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self.search_edit)
        lay.addWidget(self.list_widget, 1)
        lay.addWidget(self.empty_label)
        lay.addLayout(buttons)
        self.setWidget(body)

        self.search_edit.textChanged.connect(self._filter)
        self.list_widget.itemActivated.connect(self._emit_selected)
        self.list_widget.itemClicked.connect(self._emit_selected)
        self.copy_btn.clicked.connect(self._copy_current)
        self.delete_btn.clicked.connect(self._delete_current)
        self.clear_btn.clicked.connect(self._confirm_clear)
        self.export_btn.clicked.connect(self._export)
        self.set_sessions(())

    # ---- kamu
    def set_sessions(self, sessions: tuple[Session, ...]) -> None:
        self._sessions = tuple(reversed(sessions))  # en yeni üstte
        self.list_widget.clear()
        for s in self._sessions:
            preview = (s.corrected_text or s.raw_text).replace("\n", " ")[:PREVIEW_CHARS]
            item = QListWidgetItem(f"{s.created_at:%d.%m %H:%M}  {preview}")
            item.setData(Qt.ItemDataRole.UserRole, s)
            item.setToolTip(s.corrected_text or s.raw_text)
            self.list_widget.addItem(item)
        self.empty_label.setVisible(not self._sessions)
        self._filter(self.search_edit.text())

    # ---- iç
    def _filter(self, needle: str) -> None:
        wanted = normalize(needle)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            session = item.data(Qt.ItemDataRole.UserRole)
            haystack = normalize(f"{session.corrected_text} {session.raw_text}")
            item.setHidden(bool(wanted) and wanted not in haystack)

    def _current_session(self) -> Session | None:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _emit_selected(self, item: QListWidgetItem) -> None:
        self.session_selected.emit(item.data(Qt.ItemDataRole.UserRole))

    def _copy_current(self) -> None:
        from PySide6.QtWidgets import QApplication

        session = self._current_session()
        if session is None:
            return
        QApplication.clipboard().setText(session.corrected_text or session.raw_text)

    def _delete_current(self) -> None:
        session = self._current_session()
        if session is None:
            return
        self.delete_requested.emit(session.id)

    def _export(self) -> None:
        path, _selected_filter = self._dialog(
            self,
            "Geçmişi dışa aktar",
            "",
            "Markdown (*.md);;Metin (*.txt)",
        )
        if path:
            self.export_requested.emit(path)

    def _confirm_clear(self) -> None:
        if not self._sessions:
            return
        answer = QMessageBox.question(
            self,
            "Geçmişi temizle",
            "Tüm geçmiş kalıcı olarak silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_requested.emit()
