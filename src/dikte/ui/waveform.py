"""Kayıt göstergesindeki ses seviyesi çubukları."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from dikte.config import IndicatorSettings

BAR_COUNT = IndicatorSettings().bar_count
TICK_MS = 33


class WaveformWidget(QWidget):
    """Çubuklu seviye göstergesi: yeni tepe anında yükselir, sonra yavaşça söner."""

    def __init__(self, parent=None, color: str = "#E53935"):
        super().__init__(parent)
        self._cfg = IndicatorSettings()
        self._bars: tuple[float, ...] = (0.0,) * self._cfg.bar_count
        self._color = QColor(color)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)
        self.setMinimumHeight(40)

    def set_settings(self, cfg: IndicatorSettings) -> None:
        """Çubuk sayısı/aralığı, duyarlılık, sönüm ve kare hızı."""
        if cfg.bar_count != len(self._bars):
            self._bars = (0.0,) * cfg.bar_count
        self._cfg = cfg
        self._timer.setInterval(max(1, 1000 // cfg.fps))
        self.update()

    @property
    def bars(self) -> tuple[float, ...]:
        return self._bars

    def push_buckets(self, buckets: tuple[float, ...]) -> None:
        """0–1 arası seviye dilimlerini duyarlılıkla çarpıp çubuk sayısına örnekler."""
        src = np.clip(np.asarray(buckets, dtype=np.float32) * self._cfg.sensitivity, 0.0, 1.0)
        if src.size == 0:
            return
        idx = np.linspace(0, src.size - 1, len(self._bars))
        resampled = np.interp(idx, np.arange(src.size), src)
        # yeni değer mevcut değerden büyükse hemen yükselt, değilse tick decay'e bırak
        self._bars = tuple(max(float(n), o) for n, o in zip(resampled, self._bars, strict=True))
        self.update()

    def set_color(self, color: str) -> None:
        """Çubuk rengi (tema değişince)."""
        self._color = QColor(color)
        self.update()

    def clear(self) -> None:
        self._bars = (0.0,) * len(self._bars)
        self.update()

    def _tick(self) -> None:
        if any(self._bars):
            self._bars = tuple(v * self._cfg.decay if v > 0.01 else 0.0 for v in self._bars)
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        gap = self._cfg.bar_gap
        count = len(self._bars)
        bw = max(1.0, (w - gap * (count - 1)) / count)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        for i, v in enumerate(self._bars):
            bh = max(2.0, v * h)
            x = i * (bw + gap)
            p.drawRoundedRect(QRectF(x, (h - bh) / 2, bw, bh), bw / 2, bw / 2)
        p.end()
