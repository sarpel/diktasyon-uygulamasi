from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QFormLayout, QKeySequenceEdit, QSpinBox, QWidget

from dikte.config import Settings
from dikte.platform.hotkey_parse import (
    HotkeyParseError,
    from_key_sequence,
    to_key_sequence,
)


class GeneralTab(QWidget):
    """Kısayol, açılış davranışı ve sonucun nasıl teslim edileceği."""

    title = "Genel"

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.hotkey_edit = QKeySequenceEdit()
        self.hotkey_edit.setMaximumSequenceLength(1)
        self.hotkey_edit.setToolTip("Kısayola basarak yakalayın (ör. Ctrl+Alt+Space)")
        try:
            self.hotkey_edit.setKeySequence(to_key_sequence(settings.hotkey))
        except HotkeyParseError:
            self.hotkey_edit.setKeySequence(to_key_sequence(Settings().hotkey))

        self.autostart_check = QCheckBox("Oturum açılışında başlat")
        self.autostart_check.setChecked(settings.autostart)
        self.auto_copy_check = QCheckBox("Sonucu panoya kopyala")
        self.auto_copy_check.setChecked(settings.auto_copy)
        self.auto_paste_check = QCheckBox("Sonucu aktif pencereye yapıştır (Ctrl+V)")
        self.auto_paste_check.setChecked(settings.auto_paste)
        self.auto_paste_check.setToolTip(
            "Linux'ta xdotool (X11) veya wtype (Wayland) gerekir; yoksa metin yalnızca panoda kalır."
        )
        self.auto_paste_check.setEnabled(settings.auto_copy)
        self.auto_copy_check.toggled.connect(self.auto_paste_check.setEnabled)
        self.raise_window_check = QCheckBox("Sonuçta pencereyi öne getir")
        self.raise_window_check.setChecked(settings.raise_window_on_result)
        self.close_after_copy_check = QCheckBox("Kopyaladıktan sonra pencereyi gizle")
        self.close_after_copy_check.setChecked(settings.close_after_copy)
        self.sounds_check = QCheckBox("Başlat/durdur/hata seslerini çal")
        self.sounds_check.setChecked(settings.sounds_enabled)
        self.history_spin = QSpinBox()
        self.history_spin.setRange(0, 5000)
        self.history_spin.setSpecialValueText("Kapalı")
        self.history_spin.setValue(settings.history_limit)

        form = QFormLayout(self)
        form.addRow("Kısayol (başlat/durdur)", self.hotkey_edit)
        form.addRow("Geçmiş kayıt sayısı", self.history_spin)
        for check in (
            self.autostart_check,
            self.auto_copy_check,
            self.auto_paste_check,
            self.raise_window_check,
            self.close_after_copy_check,
            self.sounds_check,
        ):
            form.addRow(check)

    def validate(self) -> str | None:
        try:
            from_key_sequence(self.hotkey_edit.keySequence())
        except HotkeyParseError as exc:
            return str(exc)
        return None

    def apply(self, s: Settings) -> Settings:
        return s.model_copy(
            update={
                "hotkey": from_key_sequence(self.hotkey_edit.keySequence()),
                "autostart": self.autostart_check.isChecked(),
                "auto_copy": self.auto_copy_check.isChecked(),
                "auto_paste": self.auto_paste_check.isChecked(),
                "raise_window_on_result": self.raise_window_check.isChecked(),
                "close_after_copy": self.close_after_copy_check.isChecked(),
                "sounds_enabled": self.sounds_check.isChecked(),
                "history_limit": self.history_spin.value(),
            }
        )
