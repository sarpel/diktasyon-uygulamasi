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


def test_new_recording_during_error_window_does_not_leave_overlay_stuck(qtbot):
    """Hata penceresinde başlayan yeni kayıt, sonraki RESULT/IDLE'da overlay'i gizleyebilmeli."""
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_error("Konuşma algılanmadı", ms=30)
    o.on_state(DictationState.RECORDING)
    qtbot.wait(80)  # hata zamanlayıcısı jeton farkı yüzünden gizlemeyi atlar
    o.on_state(DictationState.TRANSCRIBING)
    o.on_state(DictationState.CORRECTING)
    o.on_state(DictationState.RESULT)
    assert not o.isVisible()
    o.on_state(DictationState.RECORDING)
    o.on_state(DictationState.IDLE)
    assert not o.isVisible()


def test_status_state_after_error_clears_error_flag(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_error("x", ms=5000)
    o.on_state(DictationState.TRANSCRIBING)
    o.on_state(DictationState.IDLE)
    assert not o.isVisible()


def test_error_followed_by_idle_keeps_error_visible(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_error("x", ms=5000)
    o.on_state(DictationState.IDLE)
    assert o.isVisible()


# ---- konum
def _avail():
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.primaryScreen().availableGeometry()


def test_default_position_is_bottom_center(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_recording()
    avail = _avail()
    assert o.y() == avail.bottom() - o.height() - 80
    assert abs(o.x() + o.width() // 2 - avail.center().x()) <= 1


def test_top_position_places_overlay_top_center(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.set_position("top", None)
    o.show_recording()
    avail = _avail()
    assert o.y() == avail.top() + 80
    assert abs(o.x() + o.width() // 2 - avail.center().x()) <= 1


def test_custom_position_uses_saved_xy(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    avail = _avail()
    o.set_position("custom", (avail.left() + 30, avail.top() + 40))
    o.show_recording()
    assert (o.x(), o.y()) == (avail.left() + 30, avail.top() + 40)


def test_custom_position_is_clamped_onto_screen(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    avail = _avail()
    o.set_position("custom", (avail.right() - 5, avail.bottom() - 5))
    o.show_recording()
    assert o.x() + o.width() - 1 <= avail.right()
    assert o.y() + o.height() - 1 <= avail.bottom()


def test_custom_position_off_screen_falls_back_to_bottom(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.set_position("custom", (-50000, -50000))
    o.show_recording()
    assert o.y() == _avail().bottom() - o.height() - 80


def test_custom_without_xy_falls_back_to_bottom(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.set_position("custom", None)
    o.show_recording()
    assert o.y() == _avail().bottom() - o.height() - 80


def test_dragging_overlay_moves_it_and_emits_moved(qtbot):
    from PySide6.QtCore import QPoint

    o = RecordingOverlay()
    qtbot.addWidget(o)
    avail = _avail()
    o.set_position("custom", (avail.left() + 100, avail.top() + 100))
    o.show_recording()
    qtbot.waitExposed(o)
    start = QPoint(5, 5)
    with qtbot.waitSignal(o.moved) as blocker:
        qtbot.mousePress(o, Qt.MouseButton.LeftButton, pos=start)
        qtbot.mouseMove(o, start + QPoint(20, 10))
        qtbot.mouseRelease(o, Qt.MouseButton.LeftButton, pos=start + QPoint(20, 10))
    assert blocker.args == [o.x(), o.y()]
    assert (o.x(), o.y()) == (avail.left() + 120, avail.top() + 110)
    # Uygulama ayarı kaydetmeden önce bile sonraki gösterim yeni konumda kalmalı.
    o.show_status("Yazıya dökülüyor…")
    assert (o.x(), o.y()) == (avail.left() + 120, avail.top() + 110)


def test_click_without_drag_does_not_emit_moved(qtbot):
    from PySide6.QtCore import QPoint

    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_recording()
    qtbot.waitExposed(o)
    fired = []
    o.moved.connect(lambda x, y: fired.append((x, y)))
    qtbot.mouseClick(o, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    assert fired == []


# ---- uyarı
def test_show_warning_keeps_recording_mode_and_auto_hides(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.on_state(DictationState.RECORDING)
    o.show_warning("Mikrofondan ses gelmiyor…", ms=50)
    assert o._warning.isVisible() and "Mikrofondan ses gelmiyor" in o._warning.text()
    assert o._wave.isVisible() and o._time.isVisible() and not o._status.isVisible()
    assert o._clock.isActive()
    qtbot.waitUntil(lambda: not o._warning.isVisible(), timeout=1000)
    assert o.isVisible() and o._wave.isVisible()
    o.on_state(DictationState.IDLE)  # hata yolu kullanılmadığından normal gizlenir
    assert not o.isVisible()


def test_new_recording_clears_previous_warning(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.show_recording()
    o.show_warning("uyarı", ms=5000)
    o.on_state(DictationState.TRANSCRIBING)
    assert not o._warning.isVisible()
    o.on_state(DictationState.RECORDING)
    assert not o._warning.isVisible()


def test_sphere_indicator_replaces_wave_while_recording(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.set_indicator("sphere")
    o.show_recording()
    assert o._sphere.isVisibleTo(o) and not o._wave.isVisibleTo(o)
    o.set_indicator("wave")
    assert o._wave.isVisibleTo(o) and not o._sphere.isVisibleTo(o)


def test_buckets_reach_only_the_active_indicator(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.set_indicator("sphere")
    o.show_recording()
    o.on_buckets((1.0,) * 16)
    assert o._sphere.level > 0.5
    assert max(o._wave.bars) == 0.0


def test_status_hides_both_indicators(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.set_indicator("sphere")
    o.show_recording()
    o.show_status("Çözümleniyor…")
    assert not o._sphere.isVisibleTo(o) and not o._wave.isVisibleTo(o)


def test_indicator_change_while_hidden_does_not_show_overlay(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.set_indicator("sphere")
    assert not o.isVisible()
