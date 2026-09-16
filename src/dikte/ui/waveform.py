from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

BAR_COUNT = 32
DECAY = 0.85
TICK_MS = 33


class WaveformWidget(QWidget):
    def __init__(self, parent=None, color: str = "#E53935"):
        super().__init__(parent)
        self._bars: tuple[float, ...] = (0.0,) * BAR_COUNT
        self._color = QColor(color)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)
        self.setMinimumHeight(40)

    @property
    def bars(self) -> tuple[float, ...]:
        return self._bars

    def push_buckets(self, buckets: tuple[float, ...]) -> None:
        src = np.asarray(buckets, dtype=np.float32)
        if src.size == 0:
            return
        idx = np.linspace(0, src.size - 1, BAR_COUNT)
        resampled = np.interp(idx, np.arange(src.size), src)
        # yeni değer mevcut değerden büyükse hemen yükselt, değilse tick decay'e bırak
        self._bars = tuple(max(float(n), o) for n, o in zip(resampled, self._bars))
        self.update()

    def clear(self) -> None:
        self._bars = (0.0,) * BAR_COUNT
        self.update()

    def _tick(self) -> None:
        if any(self._bars):
            self._bars = tuple(v * DECAY if v > 0.01 else 0.0 for v in self._bars)
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        gap = 2.0
        bw = max(1.0, (w - gap * (BAR_COUNT - 1)) / BAR_COUNT)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        for i, v in enumerate(self._bars):
            bh = max(2.0, v * h)
            x = i * (bw + gap)
            p.drawRoundedRect(QRectF(x, (h - bh) / 2, bw, bh), bw / 2, bw / 2)
        p.end()
