import numpy as np

from dikte.ui.sphere import POINT_COUNT, SphereWidget, fibonacci_sphere


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
    assert radii.min() >= 1.0 and radii.max() < 1.08  # yalnızca hafif "nefes"


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
