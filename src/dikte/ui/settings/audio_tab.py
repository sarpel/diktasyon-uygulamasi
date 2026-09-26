"""Ayarlar → Ses sekmesi ve giriş cihazı listesini süzme yardımcıları."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QWidget,
)

from dikte.audio.recorder import AudioRecorder
from dikte.config import Settings
from dikte.ui.settings._reset import make_reset_button, reset_row

log = logging.getLogger(__name__)
RESTART_HINT = "Sonraki kayıtta etkin olur."
MISSING_SUFFIX = " (bulunamadı)"


@dataclass(frozen=True)
class InputDevice:
    """Bir PortAudio giriş cihazı; ayarlarda index değil ad saklanır (index kayabilir)."""

    index: int
    name: str
    hostapi: str = ""  # host API adı, ör. "Windows WASAPI"; bilinmiyorsa boş


def as_input_device(item: Any) -> InputDevice:
    """(index, name[, hostapi]) demeti ya da name/index/hostapi öznitelikli nesne kabul edilir."""
    if hasattr(item, "name"):
        # Adlandırılmış demet ya da nesne; host API bir sayıysa (sounddevice index'i) adı
        # bilinmez, o zaman WASAPI süzmesi yapılamaz ama ad tekilleştirmesi yine çalışır.
        index, name = item.index, item.name
        hostapi = getattr(item, "hostapi_name", None) or getattr(item, "hostapi", "")
    else:
        index, name, *rest = item
        hostapi = rest[0] if rest else ""
    return InputDevice(int(index), str(name), hostapi if isinstance(hostapi, str) else "")


def visible_devices(
    devices: Iterable[Any], platform: str = sys.platform
) -> tuple[InputDevice, ...]:
    """Listede gösterilecek cihazlar; her ad bir kez görünür.

    Windows'ta aynı mikrofon MME, DirectSound, WASAPI ve WDM-KS altında ayrı ayrı listelenir;
    yalnızca WASAPI girişleri gösterilir (hiç yoksa hepsi)."""
    items = [as_input_device(d) for d in devices]
    if platform == "win32":
        wasapi = [d for d in items if "wasapi" in d.hostapi.lower()]
        items = wasapi or items
    seen: set[str] = set()
    unique = []
    for d in items:
        if d.name not in seen:
            seen.add(d.name)
            unique.append(d)
    return tuple(unique)


def _default_device_provider() -> tuple[Any, ...]:
    from dikte.ui.settings_dialog import list_input_devices

    return tuple(list_input_devices())


class AudioTab(QWidget):
    """Mikrofon seçimi, kayıt süresi sınırı, sessizlikte durdurma, ses gelmeyince uyarı ve
    canlı seviye testi.

    Mikrofon adıyla saklanır; kayıtlı cihaz şu an yoksa listede "(bulunamadı)" ekiyle
    seçili kalır ve bir uyarı gösterilir. Eski config'teki yalnızca-index kaydı ada çevrilir.
    """

    title = "Ses"

    def __init__(
        self,
        settings: Settings,
        devices: Iterable[Any] | None = (),
        recorder_factory: Callable[[], AudioRecorder] | None = None,
        parent=None,
        *,
        device_provider: Callable[[], Iterable[Any]] | None = None,
        platform: str = sys.platform,
    ):
        super().__init__(parent)
        self._settings = settings
        self._recorder_factory = recorder_factory or self._default_recorder
        self._recorder: AudioRecorder | None = None
        if devices is None:
            devices = (device_provider or _default_device_provider)()
        self._devices = visible_devices(devices, platform)
        self._index_by_name = {d.name: d.index for d in self._devices}

        self.device_combo = QComboBox()
        self.device_combo.setToolTip(
            f"{RESTART_HINT} Mikrofon adıyla saklanır; USB cihaz takılıp çıkınca kaymaz."
        )
        self.device_warning_label = QLabel("")
        self.device_warning_label.setWordWrap(True)
        self.device_warning_label.setStyleSheet("color:#F5A623;")

        self.max_seconds_spin = QSpinBox()
        self.max_seconds_spin.setRange(0, 36000)
        self.max_seconds_spin.setSuffix(" sn")
        self.max_seconds_spin.setSpecialValueText("Sınırsız")
        self.max_seconds_spin.setToolTip(
            "0 = sınırsız. Sınır konulursa süre dolunca kayıt otomatik durur ve çözümlenir."
        )

        self.silence_stop_spin = QDoubleSpinBox()
        self.silence_stop_spin.setRange(0, 30)
        self.silence_stop_spin.setSingleStep(0.5)
        self.silence_stop_spin.setSuffix(" sn")
        self.silence_stop_spin.setSpecialValueText("Kapalı")
        self.silence_stop_spin.setToolTip(
            "0 = kapalı. Konuşma algılandıktan sonra bu kadar sessizlik geçince kayıt "
            "otomatik durur ve çözümlenir."
        )

        self.dead_mic_spin = QDoubleSpinBox()
        self.dead_mic_spin.setRange(0, 30)
        self.dead_mic_spin.setSingleStep(0.5)
        self.dead_mic_spin.setSuffix(" sn")
        self.dead_mic_spin.setSpecialValueText("Kapalı")
        self.dead_mic_spin.setToolTip(
            "0 = kapalı. Kayıt başladıktan sonra bu kadar süre mikrofondan hiç ses "
            "gelmezse uyarı gösterilir (sessize alınmış ya da yanlış cihaz)."
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

        self.reset_btn = make_reset_button(lambda: self.load(Settings()))

        form = QFormLayout(self)
        form.addRow("Mikrofon", self.device_combo)
        form.addRow(self.device_warning_label)
        form.addRow("Kayıt süresi sınırı", self.max_seconds_spin)
        form.addRow("Sessizlikte otomatik durdurma", self.silence_stop_spin)
        form.addRow("Ses gelmeyince uyar", self.dead_mic_spin)
        form.addRow("Seviye", test_row)
        form.addRow(reset_row(self.reset_btn))

        self.load(settings)

    def load(self, settings: Settings) -> None:
        """Alanları `settings`ten doldurur; "Varsayılanlara döndür" de bunu kullanır."""
        audio = settings.audio
        self.device_combo.clear()
        self.device_combo.addItem("Sistem varsayılanı", None)
        for d in self._devices:
            self.device_combo.addItem(d.name, d.name)
        self.device_warning_label.setText("")
        self.device_warning_label.hide()
        wanted = audio.device_name
        if not wanted and audio.device_index is not None:
            # Eski config: yalnızca PortAudio index'i var; bir kez ada çevrilir.
            wanted = next((d.name for d in self._devices if d.index == audio.device_index), "")
        if wanted:
            pos = self.device_combo.findData(wanted)
            if pos < 0:
                self.device_combo.addItem(f"{wanted}{MISSING_SUFFIX}", wanted)
                pos = self.device_combo.count() - 1
                self.device_warning_label.setText(
                    f"⚠ Kayıtlı mikrofon ({wanted}) şu an bulunamadı; bağlı değilse takın "
                    "ya da listeden başka bir cihaz seçin. Bulunamazsa sistem varsayılanı "
                    "kullanılır."
                )
                self.device_warning_label.show()
            self.device_combo.setCurrentIndex(pos)
        else:
            self.device_combo.setCurrentIndex(0)
        self.max_seconds_spin.setValue(audio.max_seconds)
        self.silence_stop_spin.setValue(audio.silence_stop_s)
        self.dead_mic_spin.setValue(audio.dead_mic_warn_s)

    # ---- canlı seviye
    def _default_recorder(self) -> AudioRecorder:
        # Kayıt motoru adla çözümleyemese bile doğru cihazı açsın diye index de verilir.
        name = self.device_combo.currentData() or ""
        audio = self._settings.audio.model_copy(
            update={"device_name": name, "device_index": self._index_by_name.get(name)}
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
        # AudioRecorder.start() kendi hatasını fırlatmaz, `error` sinyaliyle bildirir —
        # bu, aynı iş parçacığında _on_recorder_error'ı (ve onun stop_test() çağrısını)
        # start()'ın kendisi dönmeden ÖNCE senkron çalıştırır. Mikrofon gerçekten
        # açılmadıysa (is_recording False) buton metnini "Testi durdur"a çevirmemeli —
        # aksi hâlde stop_test()'in düzelttiği metni hemen üzerine yazardı.
        if self._recorder is not None and getattr(self._recorder, "is_recording", True):
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
        """Mikrofon testini durdurur ve düğmeyi sıfırlar; diyalog kapanırken mikrofon açık
        kalmasın diye de çağrılır."""
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
                        "device_name": self.device_combo.currentData() or "",
                        "device_index": None,
                        "max_seconds": self.max_seconds_spin.value(),
                        "silence_stop_s": self.silence_stop_spin.value(),
                        "dead_mic_warn_s": self.dead_mic_spin.value(),
                    }
                )
            }
        )
