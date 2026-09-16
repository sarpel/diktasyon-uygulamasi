from PySide6.QtCore import Qt

from dikte.core.state import DictationState
from dikte.ui import overlay as overlay_mod
from dikte.ui.overlay import RecordingOverlay


def test_cancel_button_emits_signal(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    fired = []
    o.cancel_requested.connect(lambda: fired.append(1))
    o.show_recording()
    qtbot.mouseClick(o.cancel_btn, Qt.MouseButton.LeftButton)
    assert fired == [1]


def test_overlay_uses_screen_under_cursor(qtbot, monkeypatch):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    called = {}
    monkeypatch.setattr(
        overlay_mod.QGuiApplication,
        "screenAt",
        staticmethod(lambda pos: called.setdefault("pos", pos) and None),
    )
    o.show_recording()
    assert "pos" in called


def test_cancel_button_visible_while_recording_and_busy(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.on_state(DictationState.RECORDING)
    assert o.cancel_btn.isVisible()
    o.on_state(DictationState.TRANSCRIBING)
    assert o.cancel_btn.isVisible()


def test_show_error_is_visible_then_hides(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_error("Konuşma algılanmadı", ms=50)
    assert o.isVisible() and o._status.text().startswith("✗")
    qtbot.waitUntil(lambda: not o.isVisible(), timeout=1000)


def test_show_partial_truncates_to_last_70_chars(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_recording()
    o.show_partial("a" * 100)
    assert o._partial.text() == "…" + "a" * 70
    assert o._partial.isVisible()


def test_show_partial_short_text_not_truncated(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_recording()
    o.show_partial("kısa metin")
    assert o._partial.text() == "kısa metin"


def test_hide_overlay_clears_partial_text(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_recording()
    o.show_partial("a" * 100)
    o.hide_overlay()
    assert o._partial.text() == ""
    assert not o._partial.isVisible()


def test_show_recording_clears_previous_partial_text(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_recording()
    o.show_partial("eski parça")
    o.show_recording()
    assert o._partial.text() == ""


def test_error_hide_does_not_cancel_new_recording(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_error("x", ms=30)
    o.on_state(DictationState.RECORDING)
    qtbot.wait(80)
    assert o.isVisible() and o._wave.isVisible()
