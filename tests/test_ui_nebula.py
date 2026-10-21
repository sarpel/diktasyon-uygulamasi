import numpy as np

from dikte.config import IndicatorSettings
from dikte.ui.nebula import NebulaWidget, icosphere, loudness
from dikte.ui.nebula_shaders import FRAGMENT, VERTEX
from dikte.ui.overlay import RecordingOverlay


def make(qtbot):
    w = NebulaWidget()
    qtbot.addWidget(w)
    return w


def test_icosphere_matches_threejs_vertex_count_and_radius():
    mesh = icosphere()
    assert mesh.shape == (20 * 17 * 17 * 3, 3)  # 20 yüz × (detay+1)² üçgen × 3 köşe
    assert np.allclose(np.linalg.norm(mesh, axis=1), 1.2, atol=1e-5)


def test_shaders_declare_the_uniforms_the_widget_sets():
    for name in ("uTime", "uAudio", "uDistort", "uFreq", "uFreqBoost", "uSpin", "uBreath"):
        assert f"uniform float {name};" in VERTEX
    for name in ("uColorFrom", "uColorTo"):
        assert f"uniform vec3 {name};" in FRAGMENT
    assert VERTEX.isascii() and FRAGMENT.isascii()


def test_audio_raises_level_and_clear_resets(qtbot):
    w = make(qtbot)
    for _ in range(10):
        w.push_buckets((1.0,) * 16)
        w._tick()
    assert w.level > 0.5
    w.clear()
    assert w.level == 0.0


def test_level_decays_when_audio_stops(qtbot):
    w = make(qtbot)
    for _ in range(10):
        w.push_buckets((1.0,) * 16)
        w._tick()
    peak = w.level
    for _ in range(60):
        w._tick()
    assert w.level < peak / 2


def test_normal_speech_peaks_map_to_web_listening_range():
    """Mikrofonun ham tepe genliği küçük (konuşma ≈ 0,03–0,3); web sürümü gibi 0,4–1 aralığına
    taşınmazsa küre sese görünür tepki vermez."""
    assert loudness(0.05) >= 0.4
    assert loudness(0.3) >= 0.85
    assert loudness(0.001) == 0.0  # oda gürültüsü (−60 dBFS)


def test_color_mode_picks_colors(qtbot):
    w = make(qtbot)
    w.set_colors("#FF0000", "#00FF00")
    w.set_settings(IndicatorSettings(color_mode="theme"))
    start, end = w.qcolors()
    assert start.name() == "#ff0000" and end.name() == "#00ff00"
    w.set_settings(IndicatorSettings(color_mode="custom", custom_color="#0000FF"))
    assert w.qcolors()[0].name() == "#0000ff"


def test_overlay_routes_buckets_to_nebula(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.set_indicator("nebula")
    o.show_recording()
    o.on_buckets((1.0,) * 16)
    assert o._nebula.isVisibleTo(o) and not o._sphere.isVisibleTo(o)
    assert max(o._wave.bars) == 0.0 and o._sphere.level == 0.0
