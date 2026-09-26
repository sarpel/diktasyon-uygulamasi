"""Ayarlar → Hakkında sekmesi."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version

from PySide6.QtCore import QThreadPool, QUrl
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
from dikte.core.health import (
    check_health,
    default_cuda_probe,
    default_llm_probe,
    default_model_probe,
)
from dikte.core.workers import run_in_pool
from dikte.stt.download import download_model
from dikte.ui.health_dialog import HealthDialog

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

    GPU/VRAM ve durum kontrolü arka planda sorgulanır; hiçbir ayarı değiştirmez."""

    title = "Hakkında"

    def __init__(
        self,
        settings: Settings,
        gpu_probe: Callable[[], str] | None = None,
        vram_probe: Callable[[], str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._health_job = None
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
        self.health_btn.clicked.connect(self._open_health_dialog)
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

    def _open_health_dialog(self) -> None:
        # check_health LLM kontrolü için ağ isteği yapar (SDK yeniden deneme + zaman
        # aşımıyla dakikalarca sürebilir); GUI iş parçacığını bloke etmemek için arka
        # planda çalıştırılır.
        self.health_btn.setEnabled(False)
        self._health_job = run_in_pool(
            lambda: check_health(
                self._settings,
                cuda_probe=default_cuda_probe,
                model_probe=default_model_probe,
                llm_probe=default_llm_probe,
            ),
            self._on_health_checked,
            self._on_health_check_failed,
            QThreadPool.globalInstance(),
        )

    def _on_health_checked(self, items) -> None:
        self.health_btn.setEnabled(True)
        dlg = HealthDialog(items, on_download=self._download_model, parent=self)
        dlg.exec()

    def _on_health_check_failed(self, message: str) -> None:
        self.health_btn.setEnabled(True)
        QMessageBox.warning(self, APP_NAME, f"Durum kontrolü başarısız: {message}")

    def _download_model(self, progress) -> None:
        download_model(self._settings.stt.model, paths.models_dir(), progress)

    def validate(self) -> str | None:
        return None

    def apply(self, s: Settings) -> Settings:
        return s
