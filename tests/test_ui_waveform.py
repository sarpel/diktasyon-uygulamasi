from dikte.core.state import DictationState
from dikte.ui.overlay import RecordingOverlay
from dikte.ui.waveform import BAR_COUNT, WaveformWidget


def test_initial_bars_are_zero(qtbot):
    w = WaveformWidget()
    qtbot.addWidget(w)
    assert w.bars == (0.0,) * BAR_COUNT


def test_push_buckets_resamples_to_bar_count(qtbot):
    w = WaveformWidget()
    qtbot.addWidget(w)
    w.push_buckets((1.0,) * 8)
    assert len(w.bars) == BAR_COUNT and max(w.bars) > 0.5


def test_bars_decay_toward_zero_on_tick(qtbot):
    w = WaveformWidget()
    qtbot.addWidget(w)
    w.push_buckets((1.0,) * BAR_COUNT)
    before = w.bars[0]
    w._tick()
    assert w.bars[0] < before


def test_clear_resets(qtbot):
    w = WaveformWidget()
    qtbot.addWidget(w)
    w.push_buckets((1.0,) * BAR_COUNT)
    w.clear()
    assert w.bars == (0.0,) * BAR_COUNT


def test_paint_does_not_crash(qtbot):
    w = WaveformWidget()
    qtbot.addWidget(w)
    w.resize(300, 60)
    w.push_buckets((0.5,) * BAR_COUNT)
    w.show()
    w.grab()  # paintEvent tetikler


def test_overlay_state_transitions(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.on_state(DictationState.RECORDING)
    assert o.isVisible() and o._blink.isActive()
    o.on_buckets((0.5,) * 32)
    o.on_state(DictationState.TRANSCRIBING)
    assert o.isVisible() and not o._blink.isActive() and o._status.text() == "Yazıya dökülüyor…"
    o.on_state(DictationState.RESULT)
    assert not o.isVisible()
