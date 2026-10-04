"""Kayıt göstergesinde sese tepki veren dikenli küre.

Kürenin yüzeyine eşit aralıklı noktalar dağıtılır (Fibonacci küresi); her noktadan dışarı
doğru bir diken çıkar. Ses seviyesi yükseldikçe dikenler uzar; her dikenin boyu kendi
fazında salınan bir "gürültü" ile çarpıldığı için yüzey düzgün bir top gibi büyümez,
dikenli görünür. Küre yavaşça döner; arkada kalan dikenler soluk ve ince çizilerek
derinlik hissi verilir. Sessizlikte yalnızca hafifçe "nefes alır".

Çizim QPainter ile yapılır (GPU/OpenGL gerektirmez); geometri numpy ile vektörel
hesaplanır. Zamanlayıcı yalnızca bileşen görünürken çalışır.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

POINT_COUNT = 180
TICK_MS = 33  # ~30 kare/sn
DECAY = 0.88  # her karede seviyenin korunan oranı (yükselişte anında, inişte yumuşak)
MAX_SPIKE = 0.75  # tam seviyede en uzun dikenin yarıçapa oranı
BREATH = 0.03  # sessizlikteki "nefes" genliği (yarıçapa oranla)
SPIN_PER_TICK = 0.025  # radyan; seviye arttıkça biraz hızlanır
TILT = 0.45  # radyan; küre hafif yukarıdan görülsün

DEFAULT_COLORS = ("#E53935", "#FF8A65")  # (çekirdek/diken kökü, diken ucu)


def fibonacci_sphere(n: int) -> np.ndarray:
    """Birim küre üzerinde eşit aralıklı `n` nokta (n×3)."""
    i = np.arange(n, dtype=np.float64) + 0.5
    y = 1.0 - 2.0 * i / n
    r = np.sqrt(1.0 - y * y)
    theta = math.pi * (3.0 - math.sqrt(5.0)) * i  # altın açı
    return np.column_stack((r * np.cos(theta), y, r * np.sin(theta)))


class SphereWidget(QWidget):
    """Ses seviyesine göre dikenleri uzayan, dönen küre. `WaveformWidget` ile aynı
    arayüzü sunar (`push_buckets`, `clear`) ki overlay ikisini birbirinin yerine kullansın."""

    def __init__(self, parent=None, colors: tuple[str, str] = DEFAULT_COLORS):
        super().__init__(parent)
        self._points = fibonacci_sphere(POINT_COUNT)
        rng = np.random.default_rng(7)  # sabit tohum: her açılışta aynı karakter
        self._phase = rng.uniform(0.0, 2.0 * math.pi, POINT_COUNT)
        self._speed = rng.uniform(0.15, 0.45, POINT_COUNT)
        self._level = 0.0
        self._t = 0.0
        self._angle = 0.0
        self._base = QColor(colors[0])
        self._tip = QColor(colors[1])
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self.setMinimumSize(48, 48)

    # ---- kamu
    @property
    def level(self) -> float:
        """Yumuşatılmış ses seviyesi (0–1)."""
        return self._level

    @property
    def animating(self) -> bool:
        return self._timer.isActive()

    def set_colors(self, base: str, tip: str) -> None:
        """Çekirdek/diken kökü ve diken ucu rengi (tema değişince)."""
        self._base = QColor(base)
        self._tip = QColor(tip)
        self.update()

    def push_buckets(self, buckets: tuple[float, ...]) -> None:
        """0–1 arası seviye dilimlerinden en yükseğini alır: yükselişte anında, inişte
        `_tick` içindeki sönümle (dalga göstergesindeki davranışla aynı)."""
        if not buckets:
            return
        peak = float(np.clip(max(buckets), 0.0, 1.0))
        if peak > self._level:
            self._level = peak
            self.update()

    def clear(self) -> None:
        self._level = 0.0
        self.update()

    def spike_radii(self) -> np.ndarray:
        """Her noktanın merkezden uzaklığı, yarıçap birimiyle (≥ 1)."""
        breath = BREATH * (0.5 + 0.5 * math.sin(self._t * 1.6))
        wobble = 0.5 + 0.5 * np.sin(self._phase + self._t * self._speed * 6.0)
        # Gürültünün karesi: çoğu diken kısa, bazıları belirgin uzun → "dikenli" görünüm.
        spikes = MAX_SPIKE * self._level * (0.15 + 0.85 * wobble**2)
        return 1.0 + breath + spikes

    # ---- Qt
    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        self._t += TICK_MS / 1000.0
        self._angle += SPIN_PER_TICK * (1.0 + 2.0 * self._level)
        self._level = self._level * DECAY if self._level > 0.01 else 0.0
        self.update()

    def _projected(self) -> tuple[np.ndarray, np.ndarray]:
        """Döndürülmüş birim yönler (n×3) ve derinlik (z; +1 öne bakan)."""
        ca, sa = math.cos(self._angle), math.sin(self._angle)
        ct, st = math.cos(TILT), math.sin(TILT)
        x, y, z = self._points.T
        x1 = ca * x + sa * z  # y ekseni etrafında dönüş
        z1 = -sa * x + ca * z
        y2 = ct * y - st * z1  # x ekseni etrafında eğim
        z2 = st * y + ct * z1
        return np.column_stack((x1, y2, z2)), z2

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        # Dikenler tam uzadığında da kutuya sığsın.
        radius = min(w, h) / 2.0 / (1.0 + BREATH + MAX_SPIKE) * 0.98
        dirs, depth = self._projected()
        radii = self.spike_radii()

        # Çekirdek: yumuşak parıltılı disk.
        glow = QRadialGradient(QPointF(cx, cy), radius * (1.05 + 0.3 * self._level))
        core = QColor(self._base)
        core.setAlphaF(0.55 + 0.35 * self._level)
        edge = QColor(self._base)
        edge.setAlphaF(0.0)
        glow.setColorAt(0.0, core)
        glow.setColorAt(0.7, core)
        glow.setColorAt(1.0, edge)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, cy), radius * 1.15, radius * 1.15)

        # Dikenler arkadan öne: öndekiler arkadakilerin üstüne çizilsin.
        for i in np.argsort(depth):
            dx, dy = float(dirs[i, 0]), float(dirs[i, 1])
            front = (float(depth[i]) + 1.0) / 2.0  # 0 arka, 1 ön
            root = QPointF(cx + dx * radius, cy - dy * radius)
            tip_r = radius * float(radii[i])
            tip = QPointF(cx + dx * tip_r, cy - dy * tip_r)
            color = _mix(self._base, self._tip, min(1.0, float(radii[i]) - 1.0) * 1.6)
            color.setAlphaF(0.25 + 0.75 * front)
            pen = QPen(color, 0.8 + 1.4 * front)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(root, tip)
        p.end()


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
    )
