from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dikte.core.health import HealthItem
from dikte.core.workers import run_in_pool

log = logging.getLogger(__name__)

MODEL_ITEM_NAME = "Whisper modeli"
LLM_ITEM_NAME = "LLM"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"
OLLAMA_RECHECK_DELAY_MS = 4000  # `ollama serve` dinlemeye başlayana kadar beklenir

# Windows süreç oluşturma bayrakları; Linux'ta `subprocess` bu sabitleri tanımlamaz.
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

PullStatus = Callable[[str, int, int], None]  # (durum, tamamlanan bayt, toplam bayt)


def find_ollama() -> str | None:
    """PATH'te veya Windows'un varsayılan kurulum dizininde `ollama` yürütülebilirini arar."""
    found = shutil.which("ollama")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if sys.platform == "win32" and local:
        candidate = Path(local) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def launch_ollama_serve(
    *,
    popen: Callable[..., object] = subprocess.Popen,
    which: Callable[[], str | None] = find_ollama,
    platform: str = sys.platform,
) -> None:
    """`ollama serve`'i uygulamadan bağımsız, konsolsuz bir süreç olarak başlatır.

    Yürütülebilir bulunamazsa FileNotFoundError yükseltir.
    """
    exe = which()
    if exe is None:
        raise FileNotFoundError("ollama")
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW | DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    popen([exe, "serve"], **kwargs)


def pull_ollama_model(host: str, model: str, status: PullStatus) -> None:
    """Varsayılan `ollama pull`: SDK akışındaki her ilerleme parçasını `status`'a iletir."""
    import ollama

    client = ollama.Client(host=host)
    for part in client.pull(model, stream=True):
        status(
            getattr(part, "status", None) or "",
            getattr(part, "completed", None) or 0,
            getattr(part, "total", None) or 0,
        )


def classify_ollama_problem(item: HealthItem) -> str | None:
    """LLM satırının hata metninden Ollama sorununu çıkarır.

    `check_health` yapısal bir hata kodu döndürmediğinden metne bakılır: Ollama eksik
    modelde "model … not found, try pulling it first (status code: 404)" döndürür.
    """
    if item.ok:
        return None
    detail = item.detail.casefold()
    if "not found" in detail or "404" in detail or "pulling" in detail:
        return "model_missing"
    return "unreachable"


class HealthDialog(QDialog):
    """İlk çalıştırmada veya STT hatasında gösterilen, modal olmayan durum penceresi.

    Kapatılınca kendini siler (WA_DeleteOnClose). Bir indirme sürerken kapatılırsa
    pencere gizlenir, iş arka planda tamamlanır, arayüz güncellemeleri atlanır ve
    nesne son iş bittiğinde silinir; böylece işçi hiçbir zaman silinmiş bir nesneye
    sinyal göndermez.
    """

    model_downloaded = Signal()  # Whisper modeli başarıyla indirildi (uygulama warm_up yapar)
    _progress = Signal(int, int)  # indirme işçi iş parçacığından GUI iş parçacığına taşır
    _pull_progress = Signal(str, int, int)

    def __init__(
        self,
        items: tuple[HealthItem, ...],
        *,
        on_download: Callable[[Callable[[int, int], None]], None] | None = None,
        ollama_model: str | None = None,
        ollama_host: str = DEFAULT_OLLAMA_HOST,
        ollama_launcher: Callable[[], None] = launch_ollama_serve,
        ollama_pull: Callable[[str, str, PullStatus], None] = pull_ollama_model,
        health_probe: Callable[[], tuple[HealthItem, ...]] | None = None,
        recheck_delay_ms: int = OLLAMA_RECHECK_DELAY_MS,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Durum kontrolü")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._on_download = on_download
        self._ollama_model = ollama_model
        self._ollama_host = ollama_host
        self._ollama_launcher = ollama_launcher
        self._ollama_pull = ollama_pull
        self._health_probe = health_probe
        self._recheck_delay_ms = recheck_delay_ms
        self._jobs: dict[str, object] = {}  # run_in_pool sinyalleri: iş bitene kadar canlı
        self._closed = False
        self._labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        self._rows = QWidget()
        layout.addWidget(self._rows)

        self.download_btn = QPushButton("Modeli indir")
        self.download_btn.clicked.connect(self._start_download)
        layout.addWidget(self.download_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.start_ollama_btn = QPushButton("Ollama'yı başlat")
        self.start_ollama_btn.clicked.connect(self._start_ollama)
        layout.addWidget(self.start_ollama_btn)

        self.pull_ollama_btn = QPushButton("Modeli indir (ollama pull)")
        self.pull_ollama_btn.clicked.connect(self._confirm_and_pull)
        layout.addWidget(self.pull_ollama_btn)

        self.ollama_status = QLabel("")
        self.ollama_status.setWordWrap(True)
        self.ollama_status.setVisible(False)
        layout.addWidget(self.ollama_status)

        self.ollama_progress = QProgressBar()
        self.ollama_progress.setVisible(False)
        layout.addWidget(self.ollama_progress)

        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._progress.connect(self._on_progress)
        self._pull_progress.connect(self._on_pull_status)
        self.set_items(items)

    # ---- kamu
    def set_items(self, items: tuple[HealthItem, ...]) -> None:
        """Satırları ve tek tıkla düzeltme düğmelerini yeni kontrol sonucuna göre yeniler."""
        old = self._rows
        self._rows = QWidget()
        rows_layout = QVBoxLayout(self._rows)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        self._labels = {}
        for item in items:
            row = QHBoxLayout()
            label = QLabel(self._row_text(item))
            row.addWidget(label, 1)
            rows_layout.addLayout(row)
            self._labels[item.name] = label
            if item.hint:
                hint_label = QLabel(item.hint)
                hint_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
                rows_layout.addWidget(hint_label)
        self.layout().replaceWidget(old, self._rows)
        old.deleteLater()

        model_item = next((i for i in items if i.name == MODEL_ITEM_NAME), None)
        self.download_btn.setVisible(model_item is not None and not model_item.ok)

        llm_item = next((i for i in items if i.name == LLM_ITEM_NAME), None)
        problem = (
            classify_ollama_problem(llm_item)
            if self._ollama_model is not None and llm_item is not None
            else None
        )
        self.start_ollama_btn.setVisible(problem == "unreachable")
        self.start_ollama_btn.setEnabled(True)
        self.pull_ollama_btn.setVisible(problem == "model_missing")
        self.pull_ollama_btn.setEnabled("pull" not in self._jobs)

    # ---- yaşam döngüsü
    def showEvent(self, event) -> None:
        self._closed = False
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        if not event.spontaneous():  # simge durumuna küçültme kapanma sayılmaz
            self._closed = True
        super().hideEvent(event)

    def _begin_job(self, key: str, job: object) -> None:
        self._jobs[key] = job
        # İş sürerken Qt'nin pencereyi silmesine izin verilmez; bkz. _end_job.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

    def _end_job(self, key: str) -> None:
        self._jobs.pop(key, None)
        if self._jobs:
            return
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        if self._closed:
            self.deleteLater()

    # ---- iç
    @staticmethod
    def _row_text(item: HealthItem) -> str:
        mark = "✓" if item.ok else "✗"
        return f"{mark} {item.name}: {item.detail}"

    def _start_download(self) -> None:
        download = self._on_download
        if download is None:
            return
        self.download_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # ilk `progress` çağrısına kadar belirsiz
        self._begin_job(
            "download",
            run_in_pool(
                lambda: download(self._progress.emit),
                self._download_done,
                self._download_failed,
                QThreadPool.globalInstance(),
            ),
        )

    def _on_progress(self, done: int, total: int) -> None:
        """`_progress` sinyaline bağlı; her zaman GUI iş parçacığında çalışır (indirme
        işçi iş parçacığından widget'lara doğrudan dokunmak Qt'de güvenli değildir)."""
        if self._closed:
            return
        if total:
            self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)

    def _download_done(self, _result: object) -> None:
        self.progress_bar.setVisible(False)
        self.download_btn.setVisible(False)
        label = self._labels.get(MODEL_ITEM_NAME)
        if label is not None:
            label.setText(f"✓ {MODEL_ITEM_NAME}: önbellekte")
        self.model_downloaded.emit()
        self._end_job("download")

    def _download_failed(self, message: str) -> None:
        self.progress_bar.setVisible(False)
        self.download_btn.setEnabled(True)
        if not self._closed:
            QMessageBox.warning(self, "Durum kontrolü", f"İndirme başarısız: {message}")
        self._end_job("download")

    # ---- Ollama: başlat
    def _start_ollama(self) -> None:
        try:
            self._ollama_launcher()
        except FileNotFoundError:
            log.exception("ollama yürütülebilir dosyası bulunamadı")
            QMessageBox.warning(
                self,
                "Ollama",
                "Ollama bulunamadı. "
                f"{OLLAMA_DOWNLOAD_URL} adresinden indirip kurun, ardından yeniden deneyin.",
            )
            return
        except OSError as exc:
            log.exception("ollama serve başlatılamadı")
            QMessageBox.warning(self, "Ollama", f"Ollama başlatılamadı: {exc}")
            return
        self.start_ollama_btn.setEnabled(False)
        self._set_ollama_status("Ollama başlatılıyor… Birkaç saniye içinde yeniden denetlenecek.")
        QTimer.singleShot(self._recheck_delay_ms, self, self._recheck)

    def _recheck(self) -> None:
        probe = self._health_probe
        if probe is None:
            self.start_ollama_btn.setEnabled(True)
            self._set_ollama_status("Durumu görmek için pencereyi yeniden açın.")
            return
        if "recheck" in self._jobs:
            return
        self._begin_job(
            "recheck",
            run_in_pool(probe, self._recheck_done, self._recheck_failed),
        )

    def _recheck_done(self, result: object) -> None:
        if not self._closed:
            items = cast("tuple[HealthItem, ...]", result)
            self.set_items(items)
            llm = next((i for i in items if i.name == LLM_ITEM_NAME), None)
            if llm is not None and llm.ok:
                self.ollama_status.setVisible(False)
        self._end_job("recheck")

    def _recheck_failed(self, message: str) -> None:
        if not self._closed:
            self.start_ollama_btn.setEnabled(True)
            self._set_ollama_status(f"Durum yeniden denetlenemedi: {message}")
        self._end_job("recheck")

    # ---- Ollama: model indir
    def _confirm_and_pull(self) -> None:
        model = self._ollama_model
        if model is None or "pull" in self._jobs:
            return
        answer = QMessageBox.question(
            self,
            "Ollama modelini indir",
            f"“{model}” modeli Ollama ile indirilsin mi?\n\n"
            "Modelin boyutuna göre bu işlem birkaç GB veri indirebilir ve uzun sürebilir.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        pull, host = self._ollama_pull, self._ollama_host
        self.pull_ollama_btn.setEnabled(False)
        self._set_ollama_status(f"“{model}” indirmesi başlatılıyor…")
        self.ollama_progress.setRange(0, 0)
        self.ollama_progress.setVisible(True)
        self._begin_job(
            "pull",
            run_in_pool(
                lambda: pull(host, model, self._pull_progress.emit),
                self._pull_done,
                self._pull_failed,
                QThreadPool.globalInstance(),
            ),
        )

    def _on_pull_status(self, status: str, completed: int, total: int) -> None:
        if self._closed:
            return
        model = self._ollama_model or ""
        text = f"“{model}”: {status or 'indiriliyor'}"
        if total:
            percent = completed * 100 // total
            text += f" — %{percent}"
            self.ollama_progress.setRange(0, 100)
            self.ollama_progress.setValue(percent)
        else:
            self.ollama_progress.setRange(0, 0)
        self._set_ollama_status(text)

    def _pull_done(self, _result: object) -> None:
        if not self._closed:
            self.ollama_progress.setVisible(False)
            self.pull_ollama_btn.setVisible(False)
            self._set_ollama_status(f"✓ “{self._ollama_model}” indirildi.")
        self._jobs.pop("pull", None)
        if not self._closed:
            self._recheck()
        self._end_job("pull")

    def _pull_failed(self, message: str) -> None:
        if not self._closed:
            self.ollama_progress.setVisible(False)
            self.pull_ollama_btn.setEnabled(True)
            self._set_ollama_status(f"İndirme başarısız: {message}")
            QMessageBox.warning(
                self, "Ollama modelini indir", f"Ollama modeli indirilemedi: {message}"
            )
        self._end_job("pull")

    def _set_ollama_status(self, text: str) -> None:
        self.ollama_status.setText(text)
        self.ollama_status.setVisible(True)
