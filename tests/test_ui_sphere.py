import numpy as np

from dikte.ui.sphere import BANDS, POINT_COUNT, REST_SPIKE, SphereWidget, fibonacci_sphere


def test_fibonacci_sphere_gives_unit_vectors():
    pts = fibonacci_sphere(50)
    assert pts.shape == (50, 3)
    assert np.allclose(np.linalg.norm(pts, axis=1), 1.0)


def test_fibonacci_sphere_is_evenly_spread():
    """Noktalar bir kutupta toplanmamalı: ortalama vektör ~0."""
    pts = fibonacci_sphere(POINT_COUNT)
    assert np.linalg.norm(pts.mean(axis=0)) < 0.05


def test_silent_sphere_is_smooth(qtbot):
    w = SphereWidget()
    qtbot.addWidget(w)
    assert w.level == 0.0
    radii = w.spike_radii()
    assert radii.shape == (POINT_COUNT,)
    assert radii.min() >= 1.0 and radii.max() < 1.08  # yalnızca kısa dinlenme dikenleri


def test_loud_audio_grows_spikes(qtbot):
    w = SphereWidget()
    qtbot.addWidget(w)
    w.push_buckets((1.0,) * 16)
    assert w.level > 0.5
    radii = w.spike_radii()
    assert radii.max() > 1.3


def test_louder_audio_means_longer_spikes(qtbot):
    quiet = SphereWidget()
    loud = SphereWidget()
    qtbot.addWidget(quiet)
    qtbot.addWidget(loud)
    quiet.push_buckets((0.2,) * 16)
    loud.push_buckets((0.9,) * 16)
    assert loud.spike_radii().mean() > quiet.spike_radii().mean()


def test_spikes_are_uneven_when_loud(qtbot):
    """Dikenli görünüm: tüm noktalar aynı boyda uzarsa sadece büyüyen bir top olur."""
    w = SphereWidget()
    qtbot.addWidget(w)
    w.push_buckets((0.8,) * 16)
    assert w.spike_radii().std() > 0.05


def test_level_decays_on_tick(qtbot):
    w = SphereWidget()
    qtbot.addWidget(w)
    w.push_buckets((1.0,) * 16)
    before = w.level
    w._tick()
    assert w.level < before


def test_clear_resets_level(qtbot):
    w = SphereWidget()
    qtbot.addWidget(w)
    w.push_buckets((1.0,) * 16)
    w.clear()
    assert w.level == 0.0


def test_empty_buckets_are_ignored(qtbot):
    w = SphereWidget()
    qtbot.addWidget(w)
    w.push_buckets(())
    assert w.level == 0.0


def test_animation_runs_only_while_visible(qtbot):
    """Gizliyken her 33 ms'de bir boşuna çizim yapmasın (pil/CPU)."""
    w = SphereWidget()
    qtbot.addWidget(w)
    assert not w.animating
    w.show()
    qtbot.waitUntil(lambda: w.animating, timeout=1000)
    w.hide()
    assert not w.animating


def test_paints_without_error_silent_and_loud(qtbot):
    w = SphereWidget()
    qtbot.addWidget(w)
    w.resize(96, 96)
    assert not w.grab().isNull()
    w.push_buckets((1.0,) * 16)
    assert not w.grab().isNull()


def test_spikes_follow_their_own_band(qtbot):
    """Ses tek dilimdeyse yalnızca o dilime bağlı dikenler uzar."""
    w = SphereWidget()
    qtbot.addWidget(w)
    w.push_buckets((1.0,) + (0.0,) * (BANDS - 1))
    radii = w.spike_radii()
    quiet = radii[w._band != 0]
    assert radii[w._band == 0].max() > 1.3
    assert quiet.max() == quiet.min() == 1.0 + REST_SPIKE


def test_spin_speed_does_not_depend_on_level(qtbot):
    w = SphereWidget()
    qtbot.addWidget(w)
    w._tick()
    quiet = w._angle
    w.push_buckets((1.0,) * 16)
    w._tick()
    assert w._angle - quiet == quiet


def test_sensitivity_scales_levels(qtbot):
    from dikte.config import IndicatorSettings

    w = SphereWidget()
    qtbot.addWidget(w)
    w.set_settings(IndicatorSettings(sensitivity=4.0))
    w.push_buckets((0.2,) * 16)
    assert w.level == 0.8


def test_all_color_modes_paint(qtbot):
    from dikte.config import IndicatorSettings

    w = SphereWidget()
    qtbot.addWidget(w)
    w.resize(96, 96)
    w.push_buckets((1.0,) * 16)
    for mode in ("holo", "theme", "custom"):
        w.set_settings(IndicatorSettings(color_mode=mode, glow=0.0, core_opacity=0.0))
        assert not w.grab().isNull()


def test_core_swells_with_level(qtbot):
    from dikte.config import IndicatorSettings

    w = SphereWidget()
    qtbot.addWidget(w)
    assert w.core_scale() == 1.0
    w.push_buckets((1.0,) * 16)
    assert w.core_scale() == 1.0 + IndicatorSettings().swell
    w.set_settings(IndicatorSettings(swell=0.0))
    assert w.core_scale() == 1.0
