from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QKeySequenceEdit,
    QSpinBox,
    QWidget,
)

from dikte.config import HISTORY_LIMIT_MAX, Settings
from dikte.platform.hotkey_parse import (
    HotkeyParseError,
    from_key_sequence,
    to_key_sequence,
)
from dikte.ui.settings._reset import make_reset_button, reset_row

OVERLAY_POSITIONS = (
    ("bottom", "Altta"),
    ("top", "Üstte"),
    ("custom", "Özel (sürüklenen yer)"),
)


def _optional_hotkey(edit: QKeySequenceEdit) -> str:
    """Boş dizi = kısayol kapalı; from_key_sequence boş girdide hata verir, burada önlenir."""
    if edit.keySequence().isEmpty():
        return ""
    return from_key_sequence(edit.keySequence())


def _hotkey_edit(tooltip: str) -> QKeySequenceEdit:
    edit = QKeySequenceEdit()
    edit.setMaximumSequenceLength(1)
    edit.setToolTip(tooltip)
    return edit


def _set_optional_hotkey(edit: QKeySequenceEdit, spec: str) -> None:
    """Boş ya da çözümlenemeyen kısayol = kapalı (alan boş kalır)."""
    edit.setKeySequence(QKeySequence())
    if not spec:
        return
    try:
        edit.setKeySequence(to_key_sequence(spec))
    except HotkeyParseError:
        edit.setKeySequence(QKeySequence())


class GeneralTab(QWidget):
    """Kısayol, açılış davranışı ve sonucun nasıl teslim edileceği."""

    title = "Genel"

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.hotkey_edit = _hotkey_edit("Kısayola basarak yakalayın (ör. Ctrl+Alt+Space)")
        self.hotkey_translate_edit = _hotkey_edit("İngilizce'ye çevirip yapıştırır. Boş = kapalı.")
        self.hotkey_prompt_edit = _hotkey_edit(
            "Agent prompt'a dönüştürüp yapıştırır. Boş = kapalı."
        )
        self.hotkey_paste_last_edit = _hotkey_edit(
            "Son dikte sonucunu aktif pencereye yeniden yapıştırır. Boş = kapalı."
        )

        self.autostart_check = QCheckBox("Oturum açılışında başlat")
        self.auto_copy_check = QCheckBox("Sonucu panoya kopyala")
        self.auto_paste_check = QCheckBox("Sonucu aktif pencereye yapıştır (Ctrl+V)")
        self.auto_paste_check.setToolTip(
            "Linux'ta xdotool (X11) veya wtype (Wayland) gerekir; "
            "yoksa metin yalnızca panoda kalır."
        )
        self.auto_copy_check.toggled.connect(self.auto_paste_check.setEnabled)
        self.restore_clipboard_check = QCheckBox(
            "Yapıştırdıktan sonra eski pano içeriğini geri yükle"
        )
        self.auto_paste_check.toggled.connect(self.restore_clipboard_check.setEnabled)
        self.clipboard_exclude_history_check = QCheckBox(
            "Dikte metnini pano geçmişine ve bulut eşitlemesine alma"
        )
        self.clipboard_exclude_history_check.setToolTip(
            "Yalnızca Windows: yapıştırılan metin Win+V pano geçmişinde görünmez ve "
            "cihazlar arasında eşitlenmez. Linux'ta etkisi yoktur."
        )
        self.raise_window_check = QCheckBox("Sonuçta pencereyi öne getir")
        self.close_after_copy_check = QCheckBox("Kopyaladıktan sonra pencereyi gizle")
        self.sounds_check = QCheckBox("Başlat/durdur/hata seslerini çal")
        self.pause_media_check = QCheckBox("Kayıt sırasında çalan medyayı duraklat")
        self.pause_media_check.setToolTip(
            "Kayıt başlarken çalan müzik/video duraklatılır, kayıt bitince devam ettirilir."
        )
        self.keep_failed_audio_check = QCheckBox("Başarısız diktelerin sesini sakla")
        self.keep_failed_audio_check.setToolTip(
            "Çözümleme başarısız olursa kayıt WAV dosyası olarak saklanır; "
            "böylece söyledikleriniz kaybolmaz ve yeniden denenebilir."
        )
        self.push_to_talk_check = QCheckBox("Bas-konuş (kısayolu basılı tutunca kaydet)")
        self.push_to_talk_check.setToolTip(
            "Yalnızca Windows'ta etkindir; kısa basış her zaman aç/kapat olarak çalışır."
        )
        self.suggest_dictionary_check = QCheckBox(
            "Elle düzeltmelerden tek kelimelik sözlük önerisi çıkar"
        )
        self.voice_commands_check = QCheckBox(
            'Sesli komutları tanı ("yeni satır", "yeni paragraf", "son cümleyi sil")'
        )

        self.overlay_position_combo = QComboBox()
        for value, label in OVERLAY_POSITIONS:
            self.overlay_position_combo.addItem(label, value)
        self.overlay_position_combo.setToolTip(
            "Kayıt göstergesinin ekrandaki yeri. 'Özel' seçiliyken göstergeyi "
            "sürükleyerek bıraktığınız yer hatırlanır."
        )

        self.history_spin = QSpinBox()
        self.history_spin.setRange(0, HISTORY_LIMIT_MAX)
        self.history_spin.setSpecialValueText("Kapalı")
        self.history_spin.setToolTip(
            f"Saklanacak en fazla dikte sayısı (en çok {HISTORY_LIMIT_MAX}). 0 = geçmiş kapalı."
        )
        self.history_retention_spin = QSpinBox()
        self.history_retention_spin.setRange(0, 3650)
        self.history_retention_spin.setSuffix(" gün")
        self.history_retention_spin.setSpecialValueText("Sınırsız")
        self.history_retention_spin.setToolTip(
            "Bu kadar günden eski geçmiş kayıtları silinir. 0 = sınırsız."
        )

        self.reset_btn = make_reset_button(lambda: self.load(Settings()))

        form = QFormLayout(self)
        form.addRow("Kısayol (başlat/durdur)", self.hotkey_edit)
        form.addRow("Kısayol (çeviri)", self.hotkey_translate_edit)
        form.addRow("Kısayol (agent prompt)", self.hotkey_prompt_edit)
        form.addRow("Kısayol (son sonucu yapıştır)", self.hotkey_paste_last_edit)
        form.addRow("Gösterge konumu", self.overlay_position_combo)
        form.addRow("Geçmiş kayıt sayısı", self.history_spin)
        form.addRow("Geçmiş saklama süresi", self.history_retention_spin)
        for check in (
            self.autostart_check,
            self.auto_copy_check,
            self.auto_paste_check,
            self.restore_clipboard_check,
            self.clipboard_exclude_history_check,
            self.raise_window_check,
            self.close_after_copy_check,
            self.sounds_check,
            self.pause_media_check,
            self.keep_failed_audio_check,
            self.push_to_talk_check,
            self.suggest_dictionary_check,
            self.voice_commands_check,
        ):
            form.addRow(check)
        form.addRow(reset_row(self.reset_btn))

        self.load(settings)

    def load(self, settings: Settings) -> None:
        """Alanları `settings`ten doldurur; "Varsayılanlara döndür" de bunu kullanır."""
        try:
            self.hotkey_edit.setKeySequence(to_key_sequence(settings.hotkey))
        except HotkeyParseError:
            self.hotkey_edit.setKeySequence(to_key_sequence(Settings().hotkey))
        _set_optional_hotkey(self.hotkey_translate_edit, settings.hotkey_translate)
        _set_optional_hotkey(self.hotkey_prompt_edit, settings.hotkey_prompt)
        _set_optional_hotkey(self.hotkey_paste_last_edit, settings.hotkey_paste_last)
        self.autostart_check.setChecked(settings.autostart)
        self.auto_copy_check.setChecked(settings.auto_copy)
        self.auto_paste_check.setChecked(settings.auto_paste)
        self.restore_clipboard_check.setChecked(settings.restore_clipboard)
        self.clipboard_exclude_history_check.setChecked(settings.clipboard_exclude_history)
        self.raise_window_check.setChecked(settings.raise_window_on_result)
        self.close_after_copy_check.setChecked(settings.close_after_copy)
        self.sounds_check.setChecked(settings.sounds_enabled)
        self.pause_media_check.setChecked(settings.pause_media)
        self.keep_failed_audio_check.setChecked(settings.keep_failed_audio)
        self.push_to_talk_check.setChecked(settings.push_to_talk)
        self.suggest_dictionary_check.setChecked(settings.suggest_dictionary)
        self.voice_commands_check.setChecked(settings.voice_commands)
        pos = self.overlay_position_combo.findData(settings.overlay_position)
        self.overlay_position_combo.setCurrentIndex(max(pos, 0))
        self.history_spin.setValue(settings.history_limit)
        self.history_retention_spin.setValue(settings.history_retention_days)
        # toggled yalnızca değer değişince yayılır; bağımlı alanlar açıkça eşitlenir.
        self.auto_paste_check.setEnabled(settings.auto_copy)
        self.restore_clipboard_check.setEnabled(settings.auto_paste)

    def validate(self) -> str | None:
        try:
            main = from_key_sequence(self.hotkey_edit.keySequence())
        except HotkeyParseError as exc:
            return str(exc)
        try:
            optional = [
                _optional_hotkey(edit)
                for edit in (
                    self.hotkey_translate_edit,
                    self.hotkey_prompt_edit,
                    self.hotkey_paste_last_edit,
                )
            ]
        except HotkeyParseError as exc:
            return str(exc)
        specs = [s for s in (main, *optional) if s]
        if len(specs) != len(set(specs)):
            return "Kısayollar birbirinden farklı olmalı"
        return None

    def apply(self, s: Settings) -> Settings:
        return s.model_copy(
            update={
                "hotkey": from_key_sequence(self.hotkey_edit.keySequence()),
                "hotkey_translate": _optional_hotkey(self.hotkey_translate_edit),
                "hotkey_prompt": _optional_hotkey(self.hotkey_prompt_edit),
                "hotkey_paste_last": _optional_hotkey(self.hotkey_paste_last_edit),
                "autostart": self.autostart_check.isChecked(),
                "auto_copy": self.auto_copy_check.isChecked(),
                "auto_paste": self.auto_paste_check.isChecked(),
                "restore_clipboard": self.restore_clipboard_check.isChecked(),
                "clipboard_exclude_history": self.clipboard_exclude_history_check.isChecked(),
                "raise_window_on_result": self.raise_window_check.isChecked(),
                "close_after_copy": self.close_after_copy_check.isChecked(),
                "sounds_enabled": self.sounds_check.isChecked(),
                "pause_media": self.pause_media_check.isChecked(),
                "keep_failed_audio": self.keep_failed_audio_check.isChecked(),
                "push_to_talk": self.push_to_talk_check.isChecked(),
                "suggest_dictionary": self.suggest_dictionary_check.isChecked(),
                "voice_commands": self.voice_commands_check.isChecked(),
                "overlay_position": self.overlay_position_combo.currentData(),
                "history_limit": self.history_spin.value(),
                "history_retention_days": self.history_retention_spin.value(),
            }
        )
