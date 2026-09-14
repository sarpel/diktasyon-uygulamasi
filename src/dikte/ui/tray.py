from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from dikte.core.state import DictationState
from dikte.ui.icons import make_tray_icon

_ICON_STATE = {
    DictationState.IDLE: "idle",
    DictationState.RESULT: "idle",
    DictationState.RECORDING: "recording",
    DictationState.TRANSCRIBING: "busy",
    DictationState.CORRECTING: "busy",
}


class TrayIcon(QSystemTrayIcon):
    show_requested = Signal()
    toggle_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, hotkey_label: str, parent=None):
        super().__init__(make_tray_icon("idle"), parent)
        self._hotkey_label = hotkey_label
        self._ready = False
        self._menu = QMenu()
        menu = self._menu
        self._toggle_action = QAction("Kaydı Başlat", menu)
        self._toggle_action.triggered.connect(self.toggle_requested)
        show = QAction("Pencereyi Göster", menu)
        show.triggered.connect(self.show_requested)
        settings = QAction("Ayarlar…", menu)
        settings.triggered.connect(self.settings_requested)
        quit_ = QAction("Çıkış", menu)
        quit_.triggered.connect(self.quit_requested)
        for a in (self._toggle_action, show, settings):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(quit_)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self.set_state(DictationState.IDLE)

    def set_hotkey_label(self, label: str) -> None:
        self._hotkey_label = label
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
        self.setToolTip(f"Dikte — {status}\nKısayol: {self._hotkey_label}")

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_requested.emit()
