from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QWidget,
)

from dikte.audio.recorder import AudioRecorder
from dikte.config import Settings

log = logging.getLogger(__name__)
RESTART_HINT = "Değişiklik uygulamayı yeniden başlatınca etkin olur."


class AudioTab(QWidget):
    """Mikrofon seçimi, kayıt süresi sınırı ve canlı seviye testi."""

    title = "Ses"

    def __init__(
        self,
        settings: Settings,
        devices: tuple[tuple[int, str], ...] = (),
        recorder_factory: Callable[[], AudioRecorder] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._recorder_factory = recorder_factory or self._default_recorder
        self._recorder: AudioRecorder | None = None

        self.device_combo = QComboBox()
        self.device_combo.addItem("Sistem varsayılanı", None)
        for index, name in devices:
            self.device_combo.addItem(name, index)
        if settings.audio.device_index is not None:
            pos = self.device_combo.findData(settings.audio.device_index)
            self.device_combo.setCurrentIndex(max(pos, 0))
        self.device_combo.setToolTip(RESTART_HINT)

        self.max_seconds_spin = QSpinBox()
        self.max_seconds_spin.setRange(0, 36000)
        self.max_seconds_spin.setSuffix(" sn")
        self.max_seconds_spin.setSpecialValueText("Sınırsız")
        self.max_seconds_spin.setValue(settings.audio.max_seconds)
        self.max_seconds_spin.setToolTip(
            "0 = sınırsız. Sınır konulursa süre dolunca kayıt otomatik durur ve çözümlenir."
        )

        self.silence_stop_spin = QDoubleSpinBox()
        self.silence_stop_spin.setRange(0, 30)
        self.silence_stop_spin.setSingleStep(0.5)
        self.silence_stop_spin.setSuffix(" sn")
        self.silence_stop_spin.setSpecialValueText("Kapalı")
        self.silence_stop_spin.setValue(settings.audio.silence_stop_s)
        self.silence_stop_spin.setToolTip(
            "0 = kapalı. Konuşma algılandıktan sonra bu kadar sessizlik geçince kayıt "
            "otomatik durur ve çözümlenir."
        )

        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setTextVisible(False)
        self.test_btn = QPushButton("Mikrofonu test et")
        self.test_btn.setCheckable(True)
        self.test_btn.toggled.connect(self._toggle_test)

        test_row = QHBoxLayout()
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.level_bar, 1)

        form = QFormLayout(self)
        form.addRow("Mikrofon", self.device_combo)
        form.addRow("Kayıt süresi sınırı", self.max_seconds_spin)
        form.addRow("Sessizlikte otomatik durdurma", self.silence_stop_spin)
        form.addRow("Seviye", test_row)

    # ---- canlı seviye
    def _default_recorder(self) -> AudioRecorder:
        audio = self._settings.audio.model_copy(
            update={"device_index": self.device_combo.currentData()}
        )
        return AudioRecorder(audio)

    def _toggle_test(self, running: bool) -> None:
        if not running:
            self.stop_test()
            return
        try:
            self._recorder = self._recorder_factory()
            self._recorder.level_changed.connect(self._on_level)
            error = getattr(self._recorder, "error", None)
            if error is not None:
                error.connect(self._on_recorder_error)
            self._recorder.start()
        except Exception as exc:  # cihaz hatası diyaloğu kapatmamalı
            log.exception("mikrofon testi başlatılamadı")
            self._on_recorder_error(f"Mikrofon testi başlatılamadı: {exc}")
            return
        self.test_btn.setText("Testi durdur")

    def _on_recorder_error(self, message: str) -> None:
        """Kayıt cihazı hatası: testi durdurur ve ne yapılacağını söyler."""
        self.stop_test()
        QMessageBox.warning(
            self,
            "Mikrofon",
            f"{message}\n\nBaşka bir uygulama mikrofonu kullanıyor olabilir; "
            "Ayarlar'dan başka bir cihaz seçmeyi deneyin.",
        )

    def stop_test(self) -> None:
        """Diyalog kapanırken mikrofonun açık kalmaması için çağrılır."""
        if self._recorder is not None:
            self._recorder.stop()
            self._recorder = None
        self.level_bar.setValue(0)
        self.test_btn.setText("Mikrofonu test et")
        if self.test_btn.isChecked():
            self.test_btn.setChecked(False)

    def _on_level(self, level: float) -> None:
        self.level_bar.setValue(min(100, int(level * 300)))

    def validate(self) -> str | None:
        return None

    def apply(self, s: Settings) -> Settings:
        return s.model_copy(
            update={
                "audio": s.audio.model_copy(
                    update={
                        "device_index": self.device_combo.currentData(),
                        "max_seconds": self.max_seconds_spin.value(),
                        "silence_stop_s": self.silence_stop_spin.value(),
                    }
                )
            }
        )
