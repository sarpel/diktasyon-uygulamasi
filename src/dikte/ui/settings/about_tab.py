"""Ayarlar → Hakkında sekmesi."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version

from PySide6.QtCore import QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dikte import APP_NAME, __version__, paths
from dikte.config import Settings
from dikte.core.workers import run_in_pool

log = logging.getLogger(__name__)
PACKAGES = ("PySide6", "faster-whisper", "ctranslate2", "pydantic", "ollama")
PROBING = "Sorgulanıyor…"
UNKNOWN = "bilinmiyor"


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "kurulu değil"


def _default_gpu_probe() -> str:
    try:
        import ctranslate2  # type: ignore[import-not-found]

        if ctranslate2.get_cuda_device_count() < 1:
            return "CUDA aygıtı bulunamadı"
        types = ", ".join(sorted(ctranslate2.get_supported_compute_types("cuda")))
        return f"CUDA aygıtı var · desteklenen: {types}"
    except Exception as exc:  # noqa: BLE001 - bilgi amaçlı; hata uygulamayı durdurmamalı
        log.debug("GPU bilgisi alınamadı: %s", exc)
        return UNKNOWN


def _default_vram_probe() -> str:
    from dikte.platform.gpu_info import format_vram, query_vram

    return format_vram(query_vram())


class AboutTab(QWidget):
    """Sürüm bilgileri, GPU/VRAM durumu, log ve ayar klasörünü açma, durum kontrolü.

    GPU/VRAM arka planda sorgulanır; hiçbir ayarı değiştirmez. "Durum kontrolü…"
    `health_requested` yayar; durum penceresini uygulama açar (indirilen modeli yükler)."""

    title = "Hakkında"
    health_requested = Signal()

    def __init__(
        self,
        settings: Settings,
        gpu_probe: Callable[[], str] | None = None,
        vram_probe: Callable[[], str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        # run_in_pool'un döndürdüğü sinyal nesnesi iş bitene kadar canlı tutulur.
        self._probe_job: object | None = None
        form = QFormLayout()
        form.addRow("Uygulama", QLabel(f"{APP_NAME} {__version__}"))
        form.addRow("Python", QLabel(sys.version.split()[0]))
        for name in PACKAGES:
            form.addRow(name, QLabel(package_version(name)))
        self.gpu_label = QLabel(PROBING)
        self.gpu_label.setWordWrap(True)
        form.addRow("GPU", self.gpu_label)
        self.vram_label = QLabel(PROBING)
        form.addRow("VRAM", self.vram_label)

        self.open_log_btn = QPushButton("Log dosyasını aç")
        self.open_log_btn.clicked.connect(lambda: self._open(paths.log_path()))
        self.open_config_btn = QPushButton("Ayar klasörünü aç")
        self.open_config_btn.clicked.connect(lambda: self._open(paths.config_path().parent))
        self.health_btn = QPushButton("Durum kontrolü…")
        # Pencereyi sekme açmaz: ayarlar diyaloğu kapanınca silinir (deleteLater) ve süren
        # bir model indirmesi silinmiş nesneye yazardı; indirilen model de yüklenmezdi.
        self.health_btn.clicked.connect(self.health_requested)
        buttons = QHBoxLayout()
        buttons.addWidget(self.open_log_btn)
        buttons.addWidget(self.open_config_btn)
        buttons.addWidget(self.health_btn)
        buttons.addStretch(1)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(buttons)
        lay.addStretch(1)

        # ctranslate2 içe aktarımı ve nvidia-smi birkaç saniye sürebilir; ayarlar her
        # açıldığında GUI iş parçacığını bloke etmemek için arka planda sorgulanır.
        gpu = gpu_probe or _default_gpu_probe
        vram = vram_probe or _default_vram_probe
        self._probe_job = run_in_pool(
            lambda: (gpu(), vram()),
            self._on_probed,
            self._on_probe_failed,
            QThreadPool.globalInstance(),
        )

    def _on_probed(self, result) -> None:
        self._probe_job = None
        gpu_text, vram_text = result
        self.gpu_label.setText(gpu_text)
        self.vram_label.setText(vram_text)

    def _on_probe_failed(self, _message: str) -> None:
        # Ayrıntı run_in_pool tarafından log.exception ile günlüğe yazıldı.
        self._probe_job = None
        self.gpu_label.setText(UNKNOWN)
        self.vram_label.setText(UNKNOWN)

    def _open(self, path) -> None:
        try:
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except Exception:  # masaüstü servisi yoksa uygulama durmamalı
            log.exception("konum açılamadı: %s", path)
            opened = False
        if not opened:
            QMessageBox.warning(
                self,
                APP_NAME,
                f"{path} açılamadı. Konumu dosya yöneticinizden elle açabilirsiniz.",
            )

    def validate(self) -> str | None:
        return None

    def apply(self, s: Settings) -> Settings:
        return s
