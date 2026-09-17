from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dikte.config import Settings

COMPUTE_TYPES = ("float16", "int8_float16", "bfloat16", "int8_float32", "float32")
RESTART_HINT = "Değişince model arka planda yeniden yüklenir."


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

        self.live_chunk_spin = QSpinBox()
        self.live_chunk_spin.setRange(0, 120)
        self.live_chunk_spin.setSuffix(" sn")
        self.live_chunk_spin.setSpecialValueText("Kapalı")
        self.live_chunk_spin.setValue(int(settings.stt.live_chunk_s))
        self.live_chunk_spin.setToolTip(
            "Kayıt sırasında bu kadar konuşma + sessizlik biriktiğinde parça parça çözümlenir; "
            "overlay'de canlı metin görünür. Kapalıysa kayıt bitince tek seferde çözümlenir."
        )

        self.vad_check = QCheckBox("Sessizlik algılama (VAD) açık")
        self.vad_check.setChecked(settings.stt.vad_filter)
        self.vad_check.setToolTip(
            "Kapatılırsa sessiz kayıtlar da modele gider ve 'Altyazı M.K.' gibi uydurma "
            "metinler çıkabilir. Toplu çözümleme de VAD'e ihtiyaç duyar."
        )
        self.vad_threshold_spin = QDoubleSpinBox()
        self.vad_threshold_spin.setRange(0.0, 1.0)
        self.vad_threshold_spin.setSingleStep(0.05)
        self.vad_threshold_spin.setValue(settings.stt.vad_threshold)
        self.vad_threshold_spin.setToolTip("Gürültülü ortamda 0,60; yumuşak/kısık seste 0,35")
        self.vad_min_silence_spin = QSpinBox()
        self.vad_min_silence_spin.setRange(0, 10000)
        self.vad_min_silence_spin.setSingleStep(100)
        self.vad_min_silence_spin.setSuffix(" ms")
        self.vad_min_silence_spin.setValue(settings.stt.vad_min_silence_ms)
        self.no_speech_spin = QDoubleSpinBox()
        self.no_speech_spin.setRange(0.0, 1.0)
        self.no_speech_spin.setSingleStep(0.05)
        self.no_speech_spin.setValue(settings.stt.no_speech_threshold)
        self.no_speech_spin.setToolTip(
            "Segmentin 'konuşma değil' olasılığı bu değeri aşarsa atılır."
        )
        self.vad_speech_pad_spin = QSpinBox()
        self.vad_speech_pad_spin.setRange(0, 2000)
        self.vad_speech_pad_spin.setSingleStep(50)
        self.vad_speech_pad_spin.setSuffix(" ms")
        self.vad_speech_pad_spin.setValue(settings.stt.vad_speech_pad_ms)
        self.log_prob_spin = QDoubleSpinBox()
        self.log_prob_spin.setRange(-5.0, 0.0)
        self.log_prob_spin.setSingleStep(0.1)
        self.log_prob_spin.setDecimals(1)
        self.log_prob_spin.setValue(settings.stt.log_prob_threshold)
        self.hallucination_silence_spin = QDoubleSpinBox()
        self.hallucination_silence_spin.setRange(0.0, 30.0)
        self.hallucination_silence_spin.setSingleStep(0.5)
        self.hallucination_silence_spin.setSuffix(" sn")
        self.hallucination_silence_spin.setValue(settings.stt.hallucination_silence_threshold_s)
        self.hallucination_silence_spin.setToolTip(
            "faster-whisper yalnızca kelime zamanlarını hesapladığında bu eşiği kullanır; "
            "Dikte performans için bunu hesaplamıyor, bu yüzden bu ayarın şu an etkisi yok "
            "(aşağıdaki 'Bilinen uydurma metinleri ele' filtresi kullanın)."
        )
        self.hallucination_filter_check = QCheckBox(
            'Bilinen uydurma metinleri ele ("Altyazı M.K.", "İzlediğiniz için teşekkürler")'
        )
        self.hallucination_filter_check.setChecked(settings.stt.hallucination_filter)

        vad_group = QGroupBox("Sessizlik ve halüsinasyon")
        vad_form = QFormLayout(vad_group)
        vad_form.addRow(self.vad_check)
        vad_form.addRow("VAD eşiği", self.vad_threshold_spin)
        vad_form.addRow("En kısa sessizlik", self.vad_min_silence_spin)
        vad_form.addRow("Konuşma yok eşiği", self.no_speech_spin)
        vad_form.addRow("Konuşma dolgusu (speech pad)", self.vad_speech_pad_spin)
        vad_form.addRow("Log olasılık eşiği", self.log_prob_spin)
        vad_form.addRow("Halüsinasyon sessizlik eşiği", self.hallucination_silence_spin)
        vad_form.addRow(self.hallucination_filter_check)

        form = QFormLayout()
        form.addRow("Model", self.stt_model_edit)
        form.addRow("Hassasiyet (compute_type)", self.compute_combo)
        form.addRow("Dil", self.language_edit)
        form.addRow("Toplu çözümleme eşiği", self.batch_threshold_spin)
        form.addRow("Toplu çözümleme yığını", self.batch_size_spin)
        form.addRow(self.batch_check)
        form.addRow(self.warm_up_check)
        form.addRow("Canlı çözümleme parça süresi", self.live_chunk_spin)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(vad_group)
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
                        "live_chunk_s": float(self.live_chunk_spin.value()),
                        "vad_filter": self.vad_check.isChecked(),
                        "vad_threshold": self.vad_threshold_spin.value(),
                        "vad_min_silence_ms": self.vad_min_silence_spin.value(),
                        "no_speech_threshold": self.no_speech_spin.value(),
                        "vad_speech_pad_ms": self.vad_speech_pad_spin.value(),
                        "log_prob_threshold": self.log_prob_spin.value(),
                        "hallucination_silence_threshold_s": (
                            self.hallucination_silence_spin.value()
                        ),
                        "hallucination_filter": self.hallucination_filter_check.isChecked(),
                    }
                )
            }
        )
