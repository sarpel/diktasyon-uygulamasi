"""Kayıt göstergesinde sese tepki veren "nebula" küresi.

VoiceOrbs'un Nebula Orb'u (MIT, Alexis Munoz, github.com/amunozdev/voiceorbs): özgün WebGL
shader'ları (`nebula_shaders.py`) değiştirilmeden `QOpenGLWidget` ile GPU'da çizilir. Sahne
de özgündeki gibidir: 1,2 yarıçaplı, 16 kez bölünmüş ikosahedron; kamera 3,6 uzakta. Uniform
değerleri özgünün "listening" durumundan gelir; `uAudio` mikrofon seviyesidir. Arkadaki hale
özgündeki CSS radial-gradient'in QPainter karşılığıdır.
"""

from __future__ import annotations

import functools
import logging
import math

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QMatrix4x4,
    QOpenGLContext,
    QPainter,
    QRadialGradient,
    QSurfaceFormat,
    QVector3D,
)
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from dikte.config import IndicatorSettings
from dikte.ui.nebula_shaders import FRAGMENT, VERTEX

log = logging.getLogger(__name__)

DEFAULT_COLORS = ("#8B5CF6", "#22D3EE")  # özgün Nebula renkleri (mor → camgöbeği)
THEME_COLORS = ("#E53935", "#FF8A65")
# Özgünün "listening" durumu: bükülme, gürültü frekansı, frekans harmanı.
DISTORT = 0.34
FREQ = 1.0
FREQ_BOOST = 1.0
RESPONSE = 14.0  # seviyeye yaklaşma hızı (1/sn)
SPIN = 0.12  # radyan/sn
SHIMMER = 9.0 + 24.0  # gren fazı hızı
GLOW = 0.85  # hale saydamlığı
FLOOR_DB = -54.0  # bunun altı oda gürültüsü sayılır
RADIUS = 1.2
DETAIL = 16
CAMERA = 3.6
# Özgün 45° görüş açısında küre tuvalin ~%80'ini kaplar ve hale tuvalden taşar; burada hale
# bileşen içinde kalsın diye küre %85 oranında küçültülür (görüş açısı genişletilir).
FOV = 2.0 * math.degrees(math.atan(math.tan(math.radians(22.5)) / 0.85))
_GL_FLOAT = 0x1406
_GL_TRIANGLES = 0x0004
_GL_DEPTH_TEST = 0x0B71
_GL_COLOR_DEPTH = 0x4000 | 0x0100


def loudness(peak: float) -> float:
    """Tepe genliği → 0–1 algısal seviye: −54 dBFS altı 0, −6 dBFS üstü 1, arası doğrusal dB.
    Web sürümündeki mikrofon normalizasyonunun karşılığı: normal konuşma ≈ 0,5–0,9."""
    if peak <= 0.0:
        return 0.0
    return min(1.0, max(0.0, (20.0 * math.log10(peak) - FLOOR_DB) / (-6.0 - FLOOR_DB)))


@functools.cache
def icosphere(radius: float = RADIUS, detail: int = DETAIL) -> np.ndarray:
    """three.js `IcosahedronGeometry(radius, detail)` gibi indekssiz üçgen köşeleri (n×3)."""
    t = (1.0 + math.sqrt(5.0)) / 2.0
    verts = np.array(
        [
            (-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
            (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
            (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1),
        ],
        dtype=np.float64,
    )  # fmt: skip
    faces = (
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    )  # fmt: skip
    n = detail + 1
    tris = []
    for a, b, c in faces:
        va, vb, vc = verts[a], verts[b], verts[c]

        def point(i: int, j: int, va=va, vb=vb, vc=vc) -> np.ndarray:
            return va + (vb - va) * (i / n) + (vc - va) * (j / n)

        for i in range(n):
            for j in range(n - i):
                tris += [point(i, j), point(i + 1, j), point(i, j + 1)]
                if i + j < n - 1:
                    tris += [point(i + 1, j), point(i + 1, j + 1), point(i, j + 1)]
    pts = np.array(tris)
    return (pts / np.linalg.norm(pts, axis=1, keepdims=True) * radius).astype(np.float32)


def _linear(color: QColor) -> QVector3D:
    """sRGB → doğrusal; three.js `Color.set` renkleri shader'a böyle verir."""

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return QVector3D(channel(color.redF()), channel(color.greenF()), channel(color.blueF()))


class NebulaWidget(QOpenGLWidget):
    """Sesle bükülen nebula küresi. `SphereWidget` ile aynı arayüz (`push_buckets`, `clear`,
    `set_settings`, `set_colors`); boyut, duyarlılık, sönüm, kare hızı ve renk kipi
    `IndicatorSettings`ten gelir. Shader derlenemezse yalnızca hale çizilir ve loglanır."""

    def __init__(self, parent=None):
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        self.setFormat(fmt)
        self._theme = (QColor(THEME_COLORS[0]), QColor(THEME_COLORS[1]))
        self._level = 0.0
        self._target = 0.0
        self._t = 0.0
        self._spin = 0.0
        self._shimmer = 0.0
        self._program: QOpenGLShaderProgram | None = None
        self._vbo: QOpenGLBuffer | None = None
        self._count = 0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self.setMinimumSize(48, 48)
        self.set_settings(IndicatorSettings())

    # ---- kamu
    @property
    def level(self) -> float:
        """Yumuşatılmış ses seviyesi (0–1)."""
        return self._level

    @property
    def animating(self) -> bool:
        return self._timer.isActive()

    def set_settings(self, cfg: IndicatorSettings) -> None:
        self._cfg = cfg
        self._timer.setInterval(max(1, 1000 // cfg.fps))
        self.update()

    def set_colors(self, base: str, tip: str) -> None:
        """Tema vurgu renkleri; "theme" renk kipinde kullanılır."""
        self._theme = (QColor(base), QColor(tip))
        self.update()

    def push_buckets(self, buckets: tuple[float, ...]) -> None:
        if buckets:
            self._target = loudness(max(buckets) * self._cfg.sensitivity)

    def clear(self) -> None:
        self._level = self._target = 0.0
        self.update()

    def qcolors(self) -> tuple[QColor, QColor]:
        """Renk kipine göre (başlangıç, bitiş) rengi; holografik kipte özgün Nebula renkleri."""
        c = self._cfg
        if c.color_mode == "theme":
            return self._theme
        if c.color_mode == "custom":
            return QColor(c.custom_color), QColor(c.custom_color2)
        return QColor(DEFAULT_COLORS[0]), QColor(DEFAULT_COLORS[1])

    @property
    def shader_ready(self) -> bool:
        """Shader derlenip yüklendi mi (GL bağlamı kurulduktan sonra anlamlı)."""
        return self._program is not None

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
        self._spin = (self._spin + dt * SPIN) % (2.0 * math.pi)
        self._shimmer = (self._shimmer + dt * SHIMMER) % 1.0
        self._level += (self._target - self._level) * (1.0 - math.exp(-RESPONSE * dt))
        self._target *= self._cfg.decay ** (dt * 30.0)  # paket kesilirse sönsün
        self.update()

    def initializeGL(self) -> None:
        program = QOpenGLShaderProgram(self)
        ok = (
            program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERTEX)
            and program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAGMENT)
            and program.link()
        )
        if not ok:
            log.error("nebula shader'ı derlenemedi; yalnızca hale çizilecek:\n%s", program.log())
            return
        mesh = icosphere()
        vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        vbo.create()
        vbo.bind()
        vbo.allocate(mesh.tobytes(), mesh.nbytes)
        vbo.release()
        self._program, self._vbo, self._count = program, vbo, len(mesh)

    def paintGL(self) -> None:
        ctx = QOpenGLContext.currentContext()
        if ctx is None:
            return
        gl = ctx.functions()
        gl.glClearColor(0.0, 0.0, 0.0, 0.0)
        gl.glClear(_GL_COLOR_DEPTH)
        start, end = self.qcolors()
        p = QPainter(self)
        self._paint_halo(p, start, end)
        if self._program is not None:
            p.beginNativePainting()
            self._draw_sphere(gl, start, end)
            p.endNativePainting()
        p.end()

    def _paint_halo(self, p: QPainter, start: QColor, end: QColor) -> None:
        """Özgündeki `radial-gradient(circle at 50% 44%, to 32%, from 20% 44%, transparent 70%)`."""
        side = min(self.width(), self.height())
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        halo = QRadialGradient(QPointF(center.x(), center.y() - side * 0.06), side / 2.0 / 0.7)
        for stop, color, alpha in ((0.0, end, 0.32), (0.44, start, 0.20), (0.7, start, 0.0)):
            c = QColor(color)
            c.setAlphaF(alpha * GLOW)
            halo.setColorAt(stop, c)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(center, side / 2.0, side / 2.0)

    def _draw_sphere(self, gl, start: QColor, end: QColor) -> None:
        program, vbo = self._program, self._vbo
        assert program is not None and vbo is not None
        ratio = self.devicePixelRatio()
        side = int(min(self.width(), self.height()) * ratio)
        x = int((self.width() * ratio - side) / 2)
        y = int((self.height() * ratio - side) / 2)
        gl.glViewport(x, y, side, side)
        gl.glEnable(_GL_DEPTH_TEST)
        projection = QMatrix4x4()
        projection.perspective(FOV, 1.0, 0.1, 100.0)
        model_view = QMatrix4x4()
        model_view.translate(0.0, 0.0, -CAMERA)
        program.bind()
        program.setUniformValue(program.uniformLocation("projectionMatrix"), projection)
        program.setUniformValue(program.uniformLocation("modelViewMatrix"), model_view)
        for name, value in (
            ("uTime", self._t),
            ("uAudio", self._level),
            ("uDistort", DISTORT),
            ("uFreq", FREQ),
            ("uFreqBoost", FREQ_BOOST),
            ("uSpin", self._spin),
            ("uBreath", 1.0),
            ("uRim", 0.0),
            ("uShimmerPhase", self._shimmer),
        ):
            program.setUniformValue1f(program.uniformLocation(name), float(value))
        program.setUniformValue(program.uniformLocation("uColorFrom"), _linear(start))
        program.setUniformValue(program.uniformLocation("uColorTo"), _linear(end))
        vbo.bind()
        position = program.attributeLocation("position")
        program.enableAttributeArray(position)
        program.setAttributeBuffer(position, _GL_FLOAT, 0, 3)
        gl.glDrawArrays(_GL_TRIANGLES, 0, self._count)
        program.disableAttributeArray(position)
        vbo.release()
        program.release()
        gl.glDisable(_GL_DEPTH_TEST)
