from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from dikte.core.state import BUSY_STATES, DictationState, Session
from dikte.ui.icons import make_tray_icon

_ICON_STATE = {
    DictationState.IDLE: "idle",
    DictationState.RESULT: "idle",
    DictationState.RECORDING: "recording",
    DictationState.TRANSCRIBING: "busy",
    DictationState.CORRECTING: "busy",
}
RECENT_MENU_LIMIT = 5
RECENT_PREVIEW_CHARS = 40


class TrayIcon(QSystemTrayIcon):
    show_requested = Signal()
    toggle_requested = Signal()
    cancel_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()
    copy_requested = Signal(str)

    def __init__(self, hotkey_label: str, parent=None):
        super().__init__(make_tray_icon("idle"), parent)
        self._hotkey_label = hotkey_label
        self._mode_lines: list[str] = []
        self._ready = False
        self._recent_sessions: tuple[Session, ...] = ()
        self._menu = QMenu()
        menu = self._menu
        self._toggle_action = QAction("Kaydı Başlat", menu)
        self._toggle_action.triggered.connect(self.toggle_requested)
        self._cancel_action = QAction("Vazgeç", menu)
        self._cancel_action.triggered.connect(self.cancel_requested)
        show = QAction("Pencereyi Göster", menu)
        show.triggered.connect(self.show_requested)
        self._copy_recent_action = QAction("Son metni kopyala", menu)
        self._copy_recent_action.setEnabled(False)
        self._copy_recent_action.triggered.connect(self._emit_copy_most_recent)
        self._recent_menu = QMenu("Son dikteler", menu)
        self._recent_menu.setEnabled(False)
        settings = QAction("Ayarlar…", menu)
        settings.triggered.connect(self.settings_requested)
        quit_ = QAction("Çıkış", menu)
        quit_.triggered.connect(self.quit_requested)
        for a in (self._toggle_action, self._cancel_action, show, self._copy_recent_action):
            menu.addAction(a)
        menu.addMenu(self._recent_menu)
        menu.addAction(settings)
        menu.addSeparator()
        menu.addAction(quit_)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self.set_state(DictationState.IDLE)

    def set_recent(self, sessions: tuple[Session, ...]) -> None:
        """Tepsi menüsünde en yeni dikteyi kopyalama ve son N kaydın alt menüsünü günceller."""
        self._recent_sessions = tuple(reversed(sessions))[:RECENT_MENU_LIMIT]
        self._copy_recent_action.setEnabled(bool(self._recent_sessions))
        self._recent_menu.setEnabled(bool(self._recent_sessions))
        self._recent_menu.clear()
        for session in self._recent_sessions:
            text = session.corrected_text or session.raw_text
            preview = text.replace("\n", " ")[:RECENT_PREVIEW_CHARS] or "(boş)"
            action = QAction(preview, self._recent_menu)
            action.triggered.connect(lambda checked=False, t=text: self.copy_requested.emit(t))
            self._recent_menu.addAction(action)

    def _emit_copy_most_recent(self) -> None:
        if self._recent_sessions:
            session = self._recent_sessions[0]
            self.copy_requested.emit(session.corrected_text or session.raw_text)

    def set_hotkey_label(self, label: str) -> None:
        self._hotkey_label = label
        self._refresh_tooltip("Hazır" if self._ready else "Model yükleniyor…")

    def set_mode_labels(self, translate: str, prompt: str) -> None:
        """Çeviri/prompt kısayolları boşsa (kapalıysa) ilgili satır tooltip'te görünmez."""
        self._mode_lines = [
            line
            for line in (
                f"Çeviri: {translate}" if translate else "",
                f"Prompt: {prompt}" if prompt else "",
            )
            if line
        ]
        self._refresh_tooltip("Hazır" if self._ready else "Model yükleniyor…")

    def set_ready(self, ready: bool) -> None:
        self._ready = ready
        self._refresh_tooltip("Hazır" if ready else "Model yükleniyor…")

    def set_state(self, state: DictationState) -> None:
        self.setIcon(make_tray_icon(_ICON_STATE[state]))
        self._toggle_action.setText(
            "Kaydı Durdur" if state is DictationState.RECORDING else "Kaydı Başlat"
        )
        self._toggle_action.setEnabled(
            state not in (DictationState.TRANSCRIBING, DictationState.CORRECTING)
        )
        self._cancel_action.setEnabled(state in BUSY_STATES)
        labels = {
            DictationState.RECORDING: "Kaydediliyor",
            DictationState.TRANSCRIBING: "Yazıya dökülüyor",
            DictationState.CORRECTING: "Düzeltiliyor",
        }
        if state in labels:
            self._refresh_tooltip(labels[state])
        else:
            self.set_ready(self._ready)

    def notify(self, title: str, msg: str, critical: bool = False) -> None:
        icon = QSystemTrayIcon.Critical if critical else QSystemTrayIcon.Information
        self.showMessage(title, msg, icon, 4000)

    def _refresh_tooltip(self, status: str) -> None:
        lines = [f"Dikte — {status}", f"Kısayol: {self._hotkey_label}", *self._mode_lines]
        self.setToolTip("\n".join(lines))

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_requested.emit()
