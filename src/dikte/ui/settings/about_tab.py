from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version

from PySide6.QtCore import QUrl
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

log = logging.getLogger(__name__)
PACKAGES = ("PySide6", "faster-whisper", "ctranslate2", "pydantic", "ollama")


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "kurulu değil"


def _default_gpu_probe() -> str:
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() < 1:
            return "CUDA aygıtı bulunamadı"
        types = ", ".join(sorted(ctranslate2.get_supported_compute_types("cuda")))
        return f"CUDA aygıtı var · desteklenen: {types}"
    except Exception as exc:  # noqa: BLE001 - bilgi amaçlı; hata uygulamayı durdurmamalı
        log.debug("GPU bilgisi alınamadı: %s", exc)
        return "bilinmiyor"


class AboutTab(QWidget):
    """Sürüm bilgileri, GPU durumu ve dosya konumları."""

    title = "Hakkında"

    def __init__(self, settings: Settings, gpu_probe: Callable[[], str] | None = None, parent=None):
        super().__init__(parent)
        form = QFormLayout()
        form.addRow("Uygulama", QLabel(f"{APP_NAME} {__version__}"))
        form.addRow("Python", QLabel(sys.version.split()[0]))
        for name in PACKAGES:
            form.addRow(name, QLabel(package_version(name)))
        self.gpu_label = QLabel((gpu_probe or _default_gpu_probe)())
        self.gpu_label.setWordWrap(True)
        form.addRow("GPU", self.gpu_label)

        self.open_log_btn = QPushButton("Log dosyasını aç")
        self.open_log_btn.clicked.connect(lambda: self._open(paths.log_path()))
        self.open_config_btn = QPushButton("Ayar klasörünü aç")
        self.open_config_btn.clicked.connect(lambda: self._open(paths.config_path().parent))
        buttons = QHBoxLayout()
        buttons.addWidget(self.open_log_btn)
        buttons.addWidget(self.open_config_btn)
        buttons.addStretch(1)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(buttons)
        lay.addStretch(1)

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
