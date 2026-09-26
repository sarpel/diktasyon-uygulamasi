"""Sonuç penceresine yerleşen geçmiş paneli (dock) ve aksandan bağımsız arama."""

from __future__ import annotations

import unicodedata

from PySide6.QtCore import QEvent, Qt, Signal
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
from dikte.platform.clipboard import copy_text

PREVIEW_CHARS = 80


_DOTLESS_I = str.maketrans({"ı": "i"})  # NFKD ayrıştırmaz; elle eşlenir
SEARCH_PLACEHOLDER = "Geçmişte ara… (Ctrl+F)"


def normalize(text: str) -> str:
    """Aramayı büyük/küçük harf ve Türkçe aksanlardan bağımsız kılar.

    'İstanbul' → 'istanbul', 'toplantısı' → 'toplantisi'; böylece kullanıcı aksansız
    yazdığında da kayıtları bulabilir.
    """
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.translate(_DOTLESS_I)


class HistoryPanel(QDockWidget):
    """Geçmiş oturumlarını en yenisi üstte listeler; arama, yükleme, kopyalama, silme,
    tümünü temizleme ve dışa aktarma sağlar.

    Kopyalama panoya doğrudan yazar; diğer işlemler sinyal yayar ve kalıcı işi uygulamaya
    bırakır: `session_selected(Session)`, `delete_requested(id)`, `clear_requested`
    (onaydan sonra), `export_requested(yol)`.
    """

    session_selected = Signal(object)
    delete_requested = Signal(str)
    clear_requested = Signal()
    export_requested = Signal(str)

    def __init__(self, parent=None, dialog=None):
        super().__init__("Geçmiş", parent)
        self.setObjectName("historyDock")
        self.exclude_history = True  # Windows pano geçmişinden dışla (ayar; pencere günceller)
        self._sessions: tuple[Session, ...] = ()
        self._dialog = dialog or QFileDialog.getSaveFileName

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(SEARCH_PLACEHOLDER)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.installEventFilter(self)
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
        """Listeyi yeniden kurar (`sessions` eskiden yeniye sıralı); mevcut arama korunur."""
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

    def focus_search(self) -> None:
        self.search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_edit.selectAll()

    # ---- klavye
    # Ctrl+F ve Esc bilerek QShortcut ile değil ShortcutOverride ile yakalanır: ana pencerede
    # aynı tuşlara bağlı pencere kapsamlı kısayollar var; ikinci bir QShortcut Qt'de
    # "belirsiz kısayol" sayılır ve hiçbiri tetiklenmez. ShortcutOverride odaktaki widget'tan
    # yukarı doğru yayıldığından odak paneldeyken panel, değilse ana pencere kazanır.
    @staticmethod
    def _is_find(event) -> bool:
        return (
            event.key() == Qt.Key.Key_F and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        )

    def event(self, event) -> bool:
        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and self._is_find(
            event
        ):
            # Alt widget (ör. liste) KeyPress'i kendisi tüketebildiğinden odak burada taşınır.
            self.focus_search()
            event.accept()
            return True
        return super().event(event)

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.search_edit
            and event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)
            and event.key() == Qt.Key.Key_Escape
            and self.search_edit.text()
        ):
            event.accept()
            if event.type() == QEvent.Type.KeyPress:
                self.search_edit.clear()
            return True
        return super().eventFilter(watched, event)

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
        session = self._current_session()
        if session is None:
            return
        copy_text(session.output_text or session.raw_text, exclude_history=self.exclude_history)

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
