from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from dikte.core.health import HealthItem
from dikte.core.workers import run_in_pool

MODEL_ITEM_NAME = "Whisper modeli"


class HealthDialog(QDialog):
    """İlk çalıştırmada veya STT hatasında gösterilen, modal olmayan durum penceresi."""

    def __init__(
        self,
        items: tuple[HealthItem, ...],
        *,
        on_download: Callable[[Callable[[int, int], None]], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Durum kontrolü")
        self._on_download = on_download
        self._job_signals = None
        self._labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        for item in items:
            row = QHBoxLayout()
            label = QLabel(self._row_text(item))
            row.addWidget(label, 1)
            layout.addLayout(row)
            self._labels[item.name] = label
            if item.hint:
                hint_label = QLabel(item.hint)
                hint_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
                layout.addWidget(hint_label)

        model_item = next((i for i in items if i.name == MODEL_ITEM_NAME), None)
        self.download_btn = QPushButton("Modeli indir")
        self.download_btn.setVisible(model_item is not None and not model_item.ok)
        self.download_btn.clicked.connect(self._start_download)
        layout.addWidget(self.download_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    @staticmethod
    def _row_text(item: HealthItem) -> str:
        mark = "✓" if item.ok else "✗"
        return f"{mark} {item.name}: {item.detail}"

    def _start_download(self) -> None:
        if self._on_download is None:
            return
        self.download_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # ilk `progress` çağrısına kadar belirsiz

        def on_progress(done: int, total: int) -> None:
            if total:
                self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)

        self._job_signals = run_in_pool(
            lambda: self._on_download(on_progress),
            self._download_done,
            self._download_failed,
            QThreadPool.globalInstance(),
        )

    def _download_done(self, _result: object) -> None:
        self.progress_bar.setVisible(False)
        self.download_btn.setVisible(False)
        label = self._labels.get(MODEL_ITEM_NAME)
        if label is not None:
            label.setText(f"✓ {MODEL_ITEM_NAME}: önbellekte")

    def _download_failed(self, message: str) -> None:
        self.progress_bar.setVisible(False)
        self.download_btn.setEnabled(True)
        QMessageBox.warning(self, "Durum kontrolü", f"İndirme başarısız: {message}")
