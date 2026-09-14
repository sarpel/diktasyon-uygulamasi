from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from dikte.config import Settings
from dikte.platform.hotkey_parse import HotkeyParseError, parse_hotkey

log = logging.getLogger(__name__)


def list_input_devices() -> tuple[tuple[int, str], ...]:
    try:
        import sounddevice as sd

        return tuple(
            (i, d["name"])
            for i, d in enumerate(sd.query_devices())
            if d.get("max_input_channels", 0) > 0
        )
    except Exception:
        log.exception("ses cihazları listelenemedi")
        return ()


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, devices: tuple[tuple[int, str], ...], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dikte Ayarları")
        self._settings = settings
        form = QFormLayout()

        self.hotkey_edit = QLineEdit(settings.hotkey)
        self.hotkey_edit.setPlaceholderText("ör. ctrl+alt+space")
        self.device_combo = QComboBox()
        self.device_combo.addItem("Sistem varsayılanı", None)
        for idx, name in devices:
            self.device_combo.addItem(name, idx)
        if settings.audio.device_index is not None:
            pos = self.device_combo.findData(settings.audio.device_index)
            self.device_combo.setCurrentIndex(max(pos, 0))
        self.stt_model_edit = QLineEdit(settings.stt.model)
        self.compute_combo = QComboBox()
        self.compute_combo.addItems(
            ["float16", "int8_float16", "bfloat16", "int8_float32", "float32"]
        )
        self.compute_combo.setCurrentText(settings.stt.compute_type)
        self.llm_enabled_check = QCheckBox("LLM ile metin düzeltme (kapalıyken VRAM kullanılmaz)")
        self.llm_enabled_check.setChecked(settings.llm.enabled)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["ollama", "anthropic"])
        self.provider_combo.setCurrentText(settings.llm.provider)
        self.llm_model_edit = QLineEdit(settings.llm.model)
        self.ollama_host_edit = QLineEdit(settings.llm.ollama_host)
        self.keep_alive_edit = QLineEdit(settings.llm.keep_alive)
        self.keep_alive_edit.setToolTip(
            "Ollama modelinin bellekte kalma süresi. Düşük VRAM'de '0' yazarak "
            "her istekten sonra boşaltabilirsiniz (ör. 30m, 5m, 0)."
        )
        self._llm_widgets = (
            self.provider_combo,
            self.llm_model_edit,
            self.ollama_host_edit,
            self.keep_alive_edit,
        )
        self.llm_enabled_check.toggled.connect(self._set_llm_fields_enabled)
        self._set_llm_fields_enabled(settings.llm.enabled)
        self.batch_check = QCheckBox("Uzun kayıtlarda toplu çözümleme (daha hızlı, +VRAM)")
        self.batch_check.setChecked(settings.stt.batch_enabled)
        self.batch_threshold_spin = QSpinBox()
        self.batch_threshold_spin.setRange(5, 600)
        self.batch_threshold_spin.setSuffix(" sn")
        self.batch_threshold_spin.setValue(int(settings.stt.batch_threshold_s))
        self.batch_threshold_spin.setEnabled(settings.stt.batch_enabled)
        self.batch_check.toggled.connect(self.batch_threshold_spin.setEnabled)
        self.autostart_check = QCheckBox("Oturum açılışında başlat")
        self.autostart_check.setChecked(settings.autostart)
        self.close_after_copy_check = QCheckBox("Kopyaladıktan sonra pencereyi gizle")
        self.close_after_copy_check.setChecked(settings.close_after_copy)
        self.auto_copy_check = QCheckBox("Sonucu panoya kopyala")
        self.auto_copy_check.setChecked(settings.auto_copy)
        self.auto_paste_check = QCheckBox("Sonucu aktif pencereye yapıştır (Ctrl+V)")
        self.auto_paste_check.setChecked(settings.auto_paste)
        self.auto_paste_check.setToolTip(
            "Linux'ta xdotool (X11) veya wtype (Wayland) gerekir; yoksa metin yalnızca panoya yazılır."
        )
        self.auto_copy_check.toggled.connect(self.auto_paste_check.setEnabled)
        self.auto_paste_check.setEnabled(settings.auto_copy)
        self.raise_window_check = QCheckBox("Sonuçta pencereyi öne getir")
        self.raise_window_check.setChecked(settings.raise_window_on_result)
        self.max_seconds_spin = QSpinBox()
        self.max_seconds_spin.setRange(0, 36000)
        self.max_seconds_spin.setSuffix(" sn")
        self.max_seconds_spin.setSpecialValueText("Sınırsız")
        self.max_seconds_spin.setValue(settings.audio.max_seconds)
        self.max_seconds_spin.setToolTip(
            "0 = sınırsız kayıt. Sınır konulursa süre dolunca kayıt otomatik durur ve çözümlenir."
        )
        self.history_spin = QSpinBox()
        self.history_spin.setRange(0, 5000)
        self.history_spin.setValue(settings.history_limit)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#E53935;")

        form.addRow("Kısayol (toggle)", self.hotkey_edit)
        form.addRow("Mikrofon", self.device_combo)
        form.addRow("STT modeli", self.stt_model_edit)
        form.addRow("STT compute_type", self.compute_combo)
        form.addRow(self.llm_enabled_check)
        form.addRow("LLM sağlayıcı", self.provider_combo)
        form.addRow("LLM modeli", self.llm_model_edit)
        form.addRow("Ollama host", self.ollama_host_edit)
        form.addRow("Model bellekte kalsın", self.keep_alive_edit)
        form.addRow("Toplu çözümleme eşiği", self.batch_threshold_spin)
        form.addRow(self.batch_check)
        form.addRow("Kayıt süresi sınırı", self.max_seconds_spin)
        form.addRow("Geçmiş kayıt sayısı", self.history_spin)
        form.addRow(self.autostart_check)
        form.addRow(self.close_after_copy_check)
        form.addRow(self.auto_copy_check)
        form.addRow(self.auto_paste_check)
        form.addRow(self.raise_window_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.error_label)
        lay.addWidget(buttons)

    def _set_llm_fields_enabled(self, enabled: bool) -> None:
        for w in self._llm_widgets:
            w.setEnabled(enabled)

    def accept(self) -> None:
        try:
            parse_hotkey(self.hotkey_edit.text())
        except HotkeyParseError as exc:
            self.error_label.setText(str(exc))
            return
        if not self.stt_model_edit.text().strip():
            self.error_label.setText("STT model adı boş olamaz")
            return
        if self.llm_enabled_check.isChecked() and not self.llm_model_edit.text().strip():
            self.error_label.setText("LLM model adı boş olamaz")
            return
        super().accept()

    def result_settings(self) -> Settings:
        s = self._settings
        return s.model_copy(
            update={
                "hotkey": self.hotkey_edit.text().strip().lower(),
                "autostart": self.autostart_check.isChecked(),
                "close_after_copy": self.close_after_copy_check.isChecked(),
                "history_limit": self.history_spin.value(),
                "auto_copy": self.auto_copy_check.isChecked(),
                "auto_paste": self.auto_paste_check.isChecked(),
                "raise_window_on_result": self.raise_window_check.isChecked(),
                "stt": s.stt.model_copy(
                    update={
                        "model": self.stt_model_edit.text().strip(),
                        "compute_type": self.compute_combo.currentText(),
                        "batch_enabled": self.batch_check.isChecked(),
                        "batch_threshold_s": float(self.batch_threshold_spin.value()),
                    }
                ),
                "llm": s.llm.model_copy(
                    update={
                        "enabled": self.llm_enabled_check.isChecked(),
                        "provider": self.provider_combo.currentText(),
                        "model": self.llm_model_edit.text().strip(),
                        "ollama_host": self.ollama_host_edit.text().strip(),
                        "keep_alive": self.keep_alive_edit.text().strip() or "0",
                    }
                ),
                "audio": s.audio.model_copy(
                    update={
                        "device_index": self.device_combo.currentData(),
                        "max_seconds": self.max_seconds_spin.value(),
                    }
                ),
            }
        )
