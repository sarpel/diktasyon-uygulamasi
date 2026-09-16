from __future__ import annotations

import contextlib

from PySide6.QtWidgets import QCheckBox, QFormLayout, QKeySequenceEdit, QSpinBox, QWidget

from dikte.config import Settings
from dikte.platform.hotkey_parse import (
    HotkeyParseError,
    from_key_sequence,
    to_key_sequence,
)


def _optional_hotkey(edit: QKeySequenceEdit) -> str:
    """Boş dizi = kısayol kapalı; from_key_sequence boş girdide hata verir, burada önlenir."""
    if edit.keySequence().isEmpty():
        return ""
    return from_key_sequence(edit.keySequence())


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

        self.hotkey_translate_edit = QKeySequenceEdit()
        self.hotkey_translate_edit.setMaximumSequenceLength(1)
        self.hotkey_translate_edit.setToolTip("İngilizce'ye çevirip yapıştırır. Boş = kapalı.")
        if settings.hotkey_translate:
            with contextlib.suppress(HotkeyParseError):
                self.hotkey_translate_edit.setKeySequence(
                    to_key_sequence(settings.hotkey_translate)
                )

        self.hotkey_prompt_edit = QKeySequenceEdit()
        self.hotkey_prompt_edit.setMaximumSequenceLength(1)
        self.hotkey_prompt_edit.setToolTip("Agent prompt'a dönüştürüp yapıştırır. Boş = kapalı.")
        if settings.hotkey_prompt:
            with contextlib.suppress(HotkeyParseError):
                self.hotkey_prompt_edit.setKeySequence(to_key_sequence(settings.hotkey_prompt))

        self.autostart_check = QCheckBox("Oturum açılışında başlat")
        self.autostart_check.setChecked(settings.autostart)
        self.auto_copy_check = QCheckBox("Sonucu panoya kopyala")
        self.auto_copy_check.setChecked(settings.auto_copy)
        self.auto_paste_check = QCheckBox("Sonucu aktif pencereye yapıştır (Ctrl+V)")
        self.auto_paste_check.setChecked(settings.auto_paste)
        self.auto_paste_check.setToolTip(
            "Linux'ta xdotool (X11) veya wtype (Wayland) gerekir; "
            "yoksa metin yalnızca panoda kalır."
        )
        self.auto_paste_check.setEnabled(settings.auto_copy)
        self.auto_copy_check.toggled.connect(self.auto_paste_check.setEnabled)
        self.restore_clipboard_check = QCheckBox(
            "Yapıştırdıktan sonra eski pano içeriğini geri yükle"
        )
        self.restore_clipboard_check.setChecked(settings.restore_clipboard)
        self.restore_clipboard_check.setEnabled(settings.auto_paste)
        self.auto_paste_check.toggled.connect(self.restore_clipboard_check.setEnabled)
        self.raise_window_check = QCheckBox("Sonuçta pencereyi öne getir")
        self.raise_window_check.setChecked(settings.raise_window_on_result)
        self.close_after_copy_check = QCheckBox("Kopyaladıktan sonra pencereyi gizle")
        self.close_after_copy_check.setChecked(settings.close_after_copy)
        self.sounds_check = QCheckBox("Başlat/durdur/hata seslerini çal")
        self.sounds_check.setChecked(settings.sounds_enabled)
        self.push_to_talk_check = QCheckBox("Bas-konuş (kısayolu basılı tutunca kaydet)")
        self.push_to_talk_check.setChecked(settings.push_to_talk)
        self.push_to_talk_check.setToolTip(
            "Yalnızca Windows'ta etkindir; kısa basış her zaman aç/kapat olarak çalışır."
        )
        self.suggest_dictionary_check = QCheckBox(
            "Elle düzeltmelerden tek kelimelik sözlük önerisi çıkar"
        )
        self.suggest_dictionary_check.setChecked(settings.suggest_dictionary)
        self.voice_commands_check = QCheckBox(
            'Sesli komutları tanı ("yeni satır", "yeni paragraf", "son cümleyi sil")'
        )
        self.voice_commands_check.setChecked(settings.voice_commands)
        self.history_spin = QSpinBox()
        self.history_spin.setRange(0, 5000)
        self.history_spin.setSpecialValueText("Kapalı")
        self.history_spin.setValue(settings.history_limit)

        form = QFormLayout(self)
        form.addRow("Kısayol (başlat/durdur)", self.hotkey_edit)
        form.addRow("Kısayol (çeviri)", self.hotkey_translate_edit)
        form.addRow("Kısayol (agent prompt)", self.hotkey_prompt_edit)
        form.addRow("Geçmiş kayıt sayısı", self.history_spin)
        for check in (
            self.autostart_check,
            self.auto_copy_check,
            self.auto_paste_check,
            self.restore_clipboard_check,
            self.raise_window_check,
            self.close_after_copy_check,
            self.sounds_check,
            self.push_to_talk_check,
            self.suggest_dictionary_check,
            self.voice_commands_check,
        ):
            form.addRow(check)

    def validate(self) -> str | None:
        try:
            main = from_key_sequence(self.hotkey_edit.keySequence())
        except HotkeyParseError as exc:
            return str(exc)
        try:
            translate = _optional_hotkey(self.hotkey_translate_edit)
            prompt = _optional_hotkey(self.hotkey_prompt_edit)
        except HotkeyParseError as exc:
            return str(exc)
        specs = [s for s in (main, translate, prompt) if s]
        if len(specs) != len(set(specs)):
            return "Kısayollar birbirinden farklı olmalı"
        return None

    def apply(self, s: Settings) -> Settings:
        return s.model_copy(
            update={
                "hotkey": from_key_sequence(self.hotkey_edit.keySequence()),
                "hotkey_translate": _optional_hotkey(self.hotkey_translate_edit),
                "hotkey_prompt": _optional_hotkey(self.hotkey_prompt_edit),
                "autostart": self.autostart_check.isChecked(),
                "auto_copy": self.auto_copy_check.isChecked(),
                "auto_paste": self.auto_paste_check.isChecked(),
                "restore_clipboard": self.restore_clipboard_check.isChecked(),
                "raise_window_on_result": self.raise_window_check.isChecked(),
                "close_after_copy": self.close_after_copy_check.isChecked(),
                "sounds_enabled": self.sounds_check.isChecked(),
                "push_to_talk": self.push_to_talk_check.isChecked(),
                "suggest_dictionary": self.suggest_dictionary_check.isChecked(),
                "voice_commands": self.voice_commands_check.isChecked(),
                "history_limit": self.history_spin.value(),
            }
        )
