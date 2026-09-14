from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dikte.config import Settings

COMPUTE_TYPES = ("float16", "int8_float16", "bfloat16", "int8_float32", "float32")
RESTART_HINT = "Değişiklik uygulamayı yeniden başlatınca etkin olur."


class SttTab(QWidget):
    """Whisper modeli, hassasiyet, toplu çözümleme ve ısınma."""

    title = "Konuşma Tanıma"

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.stt_model_edit = QLineEdit(settings.stt.model)
        self.stt_model_edit.setToolTip(RESTART_HINT)
        self.compute_combo = QComboBox()
        self.compute_combo.addItems(COMPUTE_TYPES)
        self.compute_combo.setCurrentText(settings.stt.compute_type)
        self.compute_combo.setToolTip(
            f"{RESTART_HINT} GPU desteklemiyorsa otomatik olarak desteklenen bir tipe düşülür."
        )
        self.language_edit = QLineEdit(settings.stt.language)
        self.language_edit.setToolTip("ISO kodu, ör. tr")

        self.batch_check = QCheckBox("Uzun kayıtlarda toplu çözümleme (daha hızlı, +VRAM)")
        self.batch_check.setChecked(settings.stt.batch_enabled)
        self.batch_threshold_spin = QSpinBox()
        self.batch_threshold_spin.setRange(5, 600)
        self.batch_threshold_spin.setSuffix(" sn")
        self.batch_threshold_spin.setValue(int(settings.stt.batch_threshold_s))
        self.batch_threshold_spin.setEnabled(settings.stt.batch_enabled)
        self.batch_check.toggled.connect(self.batch_threshold_spin.setEnabled)
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(1, 32)
        self.batch_size_spin.setValue(settings.stt.batch_size)
        self.batch_size_spin.setEnabled(settings.stt.batch_enabled)
        self.batch_check.toggled.connect(self.batch_size_spin.setEnabled)

        self.warm_up_check = QCheckBox("Açılışta modeli ısıt (ilk diktedeki gecikmeyi alır)")
        self.warm_up_check.setChecked(settings.stt.warm_up)

        form = QFormLayout()
        form.addRow("Model", self.stt_model_edit)
        form.addRow("Hassasiyet (compute_type)", self.compute_combo)
        form.addRow("Dil", self.language_edit)
        form.addRow("Toplu çözümleme eşiği", self.batch_threshold_spin)
        form.addRow("Toplu çözümleme yığını", self.batch_size_spin)
        form.addRow(self.batch_check)
        form.addRow(self.warm_up_check)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addStretch(1)

    def validate(self) -> str | None:
        if not self.stt_model_edit.text().strip():
            return "STT model adı boş olamaz"
        if not self.language_edit.text().strip():
            return "Dil kodu boş olamaz"
        return None

    def apply(self, s: Settings) -> Settings:
        return s.model_copy(
            update={
                "stt": s.stt.model_copy(
                    update={
                        "model": self.stt_model_edit.text().strip(),
                        "compute_type": self.compute_combo.currentText(),
                        "language": self.language_edit.text().strip(),
                        "batch_enabled": self.batch_check.isChecked(),
                        "batch_threshold_s": float(self.batch_threshold_spin.value()),
                        "batch_size": self.batch_size_spin.value(),
                        "warm_up": self.warm_up_check.isChecked(),
                    }
                )
            }
        )
