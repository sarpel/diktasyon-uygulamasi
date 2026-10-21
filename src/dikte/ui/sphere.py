"""Kayıt göstergesinde sese tepki veren dikenli küre.

Kürenin yüzeyine eşit aralıklı noktalar dağıtılır (Fibonacci küresi); her noktadan dışarı
doğru bir diken çıkar. Sese yalnızca dikenler tepki verir: her diken bir ses dilimine
bağlıdır ve o dilimin seviyesiyle uzayıp kısalır. Kürenin kendisi (yarıçap, konum, dönüş
hızı) sabittir; sallanmaz. Neon/holografik görünüm için toplamalı (additive) karışım ve
yöne göre kayan cyan–magenta renk tonu kullanılır.

Çizim QPainter ile yapılır (GPU/OpenGL gerektirmez); geometri numpy ile vektörel
hesaplanır. Zamanlayıcı yalnızca bileşen görünürken çalışır.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from dikte.config import IndicatorSettings

_DEFAULTS = IndicatorSettings()
POINT_COUNT = _DEFAULTS.point_count
REST_SPIKE = _DEFAULTS.rest_spike
BANDS = 16  # ses dilimi sayısı; her diken birine bağlı
TICK_MS = 33  # ~30 kare/sn (ayarla değişir)

DEFAULT_COLORS = ("#E53935", "#FF8A65")  # (tema vurgusu, tema ikinci vurgusu)


def fibonacci_sphere(n: int) -> np.ndarray:
    """Birim küre üzerinde eşit aralıklı `n` nokta (n×3)."""
    i = np.arange(n, dtype=np.float64) + 0.5
    y = 1.0 - 2.0 * i / n
    r = np.sqrt(1.0 - y * y)
    theta = math.pi * (3.0 - math.sqrt(5.0)) * i  # altın açı
    return np.column_stack((r * np.cos(theta), y, r * np.sin(theta)))


class SphereWidget(QWidget):
    """Ses seviyesine göre dikenleri uzayan, dönen küre. `WaveformWidget` ile aynı
    arayüzü sunar (`push_buckets`, `clear`, `set_settings`) ki overlay ikisini birbirinin
    yerine kullansın. Tüm görünüm `IndicatorSettings` ile ayarlanır."""

    def __init__(self, parent=None, colors: tuple[str, str] = DEFAULT_COLORS):
        super().__init__(parent)
        self._base = QColor(colors[0])
        self._tip = QColor(colors[1])
        self._levels = np.zeros(BANDS)
        self._t = 0.0
        self._angle = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setMinimumSize(48, 48)
        self.set_settings(_DEFAULTS)

    # ---- kamu
    @property
    def level(self) -> float:
        """Yumuşatılmış en yüksek dilim seviyesi (0–1)."""
        return float(self._levels.max())

    @property
    def animating(self) -> bool:
        return self._timer.isActive()

    @property
    def settings(self) -> IndicatorSettings:
        return self._cfg

    def set_settings(self, cfg: IndicatorSettings) -> None:
        """Görünüm ayarlarını uygular; diken sayısı değiştiyse noktalar yeniden dağıtılır."""
        if getattr(self, "_cfg", None) is None or cfg.point_count != self._cfg.point_count:
            self._points = fibonacci_sphere(cfg.point_count)
            rng = np.random.default_rng(7)  # sabit tohum: her açılışta aynı karakter
            self._phase = rng.uniform(0.0, 2.0 * math.pi, cfg.point_count)
            self._speed = rng.uniform(0.15, 0.45, cfg.point_count)
            self._band = rng.integers(0, BANDS, cfg.point_count)
        self._cfg = cfg
        self._timer.setInterval(max(1, 1000 // cfg.fps))
        self.update()

    def set_colors(self, base: str, tip: str) -> None:
        """Tema vurgu renkleri; "theme" renk kipinde dikenler bunlarla boyanır."""
        self._base = QColor(base)
        self._tip = QColor(tip)
        self.update()

    def push_buckets(self, buckets: tuple[float, ...]) -> None:
        """0–1 arası seviye dilimlerini `BANDS` dilime örnekler: yükselişte anında, inişte
        `_tick` içindeki sönümle (dalga göstergesindeki davranışla aynı)."""
        if not buckets:
            return
        src = np.clip(np.asarray(buckets, dtype=np.float64) * self._cfg.sensitivity, 0.0, 1.0)
        new = np.interp(np.linspace(0, src.size - 1, BANDS), np.arange(src.size), src)
        self._levels = np.maximum(self._levels, new)
        self.update()

    def clear(self) -> None:
        self._levels = np.zeros(BANDS)
        self.update()

    def spike_radii(self) -> np.ndarray:
        """Her noktanın merkezden uzaklığı, yarıçap birimiyle (≥ 1)."""
        c = self._cfg
        wobble = 0.5 + 0.5 * np.sin(self._phase + self._t * self._speed * 6.0)
        # Gürültünün karesi: çoğu diken kısa, bazıları belirgin uzun → "dikenli" görünüm.
        shape = (1.0 - c.spikiness) + c.spikiness * wobble**2
        return 1.0 + c.rest_spike + c.max_spike * self._levels[self._band] * shape

    # ---- Qt
    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        dt = self._timer.interval() / 1000.0
        self._t += dt
        self._angle += self._cfg.spin_speed * dt
        decayed = self._levels * self._cfg.decay
        self._levels = np.where(decayed > 0.01, decayed, 0.0)
        self.update()

    def _projected(self) -> tuple[np.ndarray, np.ndarray]:
        """Döndürülmüş birim yönler (n×3) ve derinlik (z; +1 öne bakan)."""
        ca, sa = math.cos(self._angle), math.sin(self._angle)
        ct, st = math.cos(self._cfg.tilt), math.sin(self._cfg.tilt)
        x, y, z = self._points.T
        x1 = ca * x + sa * z  # y ekseni etrafında dönüş
        z1 = -sa * x + ca * z
        y2 = ct * y - st * z1  # x ekseni etrafında eğim
        z2 = st * y + ct * z1
        return np.column_stack((x1, y2, z2)), z2

    def _spike_color(self, mix: float, saturation: float, alpha: float) -> QColor:
        """`mix` (0–1) iki uç renk arasındaki konum; kipe göre ton ya da RGB karışımı."""
        c = self._cfg
        if c.color_mode == "holo":
            hue = c.hue_low + (c.hue_high - c.hue_low) * mix
            return QColor.fromHsvF(hue % 1.0, saturation, 1.0, min(1.0, alpha))
        a, b = (
            (self._base, self._tip)
            if c.color_mode == "theme"
            else (QColor(c.custom_color), QColor(c.custom_color2))
        )
        # Düşük doygunluk = beyaza yakın: uzayan diken ucu parlasın (holo kipiyle aynı his).
        white = max(0.0, min(1.0, 1.0 - saturation / 0.9))
        rgb = [
            (x + (y - x) * mix) * (1.0 - white) + white
            for x, y in zip(a.getRgbF()[:3], b.getRgbF()[:3], strict=True)
        ]
        return QColor.fromRgbF(*rgb, min(1.0, alpha))

    def paintEvent(self, event) -> None:
        c = self._cfg
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        center = QPointF(cx, cy)
        # Dikenler tam uzadığında da kutuya sığsın; yarıçap sese göre değişmez.
        radius = min(w, h) / 2.0 / (1.0 + c.rest_spike + c.max_spike) * 0.98
        dirs, depth = self._projected()
        radii = self.spike_radii()
        # Toplamalı karışım: üst üste binen ışık parlar (neon).
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        # Çekirdek: içi koyu, kenarı parlayan cam küre (fresnel halkası) + tema tonu.
        if c.core_opacity > 0:
            rim = QRadialGradient(center, radius)
            for stop, alpha in ((0.0, 0.05), (0.75, 0.12), (0.97, 0.55), (1.0, 0.0)):
                rim.setColorAt(stop, self._spike_color(0.3, 0.6, alpha * c.core_opacity))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(rim)
            p.drawEllipse(center, radius, radius)
            tint = QColor(self._base)
            tint.setAlphaF(min(1.0, 0.12 * c.core_opacity))
            p.setBrush(tint)
            p.drawEllipse(center, radius * 0.6, radius * 0.6)

        for i in np.argsort(depth):
            dx, dy = float(dirs[i, 0]), float(dirs[i, 1])
            front = (float(depth[i]) + 1.0) / 2.0  # 0 arka, 1 ön
            root = QPointF(cx + dx * radius, cy - dy * radius)
            tip_r = radius * float(radii[i])
            tip = QPointF(cx + dx * tip_r, cy - dy * tip_r)
            # Yön ve zamanla kayan renk: dönen hologram yanardönerliği.
            mix = 0.5 + 0.5 * math.sin(3.0 * dx + 2.0 * dy + self._t * c.shimmer_speed)
            grow = min(1.0, (float(radii[i]) - 1.0 - c.rest_spike) / c.max_spike * 1.5)
            pens = [
                QPen(
                    self._spike_color(mix, 0.65 - 0.45 * grow, 0.25 + 0.7 * front),
                    (0.6 + 0.9 * front) * c.line_width,
                )
            ]
            if c.glow > 0:
                glow_color = self._spike_color(mix, 0.9, (0.10 + 0.15 * front) * c.glow)
                pens.insert(0, QPen(glow_color, (2.5 + 2.5 * front) * c.line_width))
            for pen in pens:
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(root, tip)
        p.end()
