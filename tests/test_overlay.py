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
    qtbot.mouseClick(o.cancel_btn, Qt.LeftButton)
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
