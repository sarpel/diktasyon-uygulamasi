import logging
import sys

import pytest
from PySide6.QtCore import Qt

from dikte import app as app_mod
from dikte.config import LlmSettings, Settings
from dikte.core.state import DictationState, Session
from dikte.llm.provider import LlmError
from dikte.logging_setup import setup_logging
from dikte.ui.icons import copy_icon, make_tray_icon
from dikte.ui.toast import Toast


@pytest.fixture
def ctx(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod.paths, "history_path", lambda: tmp_path / "history.jsonl")
    c = app_mod.build_app(Settings())
    for w in (c.window, c.overlay):
        qtbot.addWidget(w)
    return c


def test_build_app_returns_wired_context(ctx):
    assert ctx.controller.state is DictationState.IDLE
    assert ctx.window._controller is ctx.controller
    assert "Ctrl+Alt+Space" in ctx.tray.toolTip()


def test_state_changes_propagate_to_tray_and_overlay(ctx, qtbot):
    ctx.controller.state_changed.emit(DictationState.RECORDING)
    assert ctx.overlay.isVisible()
    assert ctx.tray._toggle_action.text() == "Kaydı Durdur"
    ctx.controller.state_changed.emit(DictationState.IDLE)
    assert not ctx.overlay.isVisible()


def test_result_state_appends_history(ctx):
    ctx.controller._update_session(raw_text="a", corrected_text="A.")
    ctx.controller.state_changed.emit(DictationState.RESULT)
    assert [s.corrected_text for s in ctx.history.load()] == ["A."]


def test_session_updates_reach_window(ctx):
    ctx.controller.session_updated.emit(Session(raw_text="ham", corrected_text="Düzeltilmiş."))
    assert ctx.window.raw_pane.text() == "ham"
    assert ctx.window.corrected_pane.text() == "Düzeltilmiş."


def test_make_llm_falls_back_to_null_provider_on_error(monkeypatch):
    def boom(_settings):
        raise LlmError("yok")

    monkeypatch.setattr(app_mod, "make_provider", boom)
    provider = app_mod._make_llm(Settings())
    assert provider.name == "none"
    with pytest.raises(LlmError):
        provider.complete("s", "u")


def test_make_llm_returns_configured_provider():
    assert app_mod._make_llm(Settings(llm=LlmSettings())).name == "ollama"


def test_setup_logging_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("dikte.paths.log_path", lambda: tmp_path / "dikte.log")
    root = logging.getLogger()
    saved, root.handlers = root.handlers, []
    try:
        setup_logging("DEBUG")
        count = len(root.handlers)
        setup_logging("DEBUG")
        assert count >= 1 and len(root.handlers) == count
        logging.getLogger("t").debug("merhaba")
        assert (tmp_path / "dikte.log").exists()
    finally:
        for h in root.handlers:
            h.close()
        root.handlers = saved


def test_icons_are_not_null():
    assert not make_tray_icon("recording").isNull()
    assert not copy_icon().isNull()


def test_toast_shows_and_is_centered(qtbot):
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(400, 300)
    parent.show()
    t = Toast.show_message(parent, "Kopyalandı")
    assert t.isVisible() and t.text() == "Kopyalandı"
    assert 0 <= t.x() <= parent.width() - t.width()


def test_open_settings_applies_new_settings(ctx, monkeypatch, tmp_path):
    saved = {}
    monkeypatch.setattr(app_mod, "save_settings", lambda s: saved.update(hotkey=s.hotkey))
    monkeypatch.setattr(app_mod, "set_autostart", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "list_input_devices", lambda: ())
    monkeypatch.setattr(app_mod.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    class FakeDialog:
        def __init__(self, settings, devices, parent=None):
            self._settings = settings

        def exec(self):
            return 1  # QDialog.DialogCode.Accepted

        def result_settings(self):
            return self._settings.model_copy(
                update={"hotkey": "ctrl+shift+d", "close_after_copy": True}
            )

    monkeypatch.setattr(app_mod, "SettingsDialog", FakeDialog)
    app_mod._open_settings(ctx)
    assert ctx.settings.hotkey == "ctrl+shift+d" and saved["hotkey"] == "ctrl+shift+d"
    assert ctx.window.close_after_copy is True
    expected = "ctrl+shift+d" if sys.platform == "win32" else app_mod.CLI_TOGGLE_HINT
    assert expected in ctx.tray.toolTip().lower()


def test_open_settings_cancelled_changes_nothing(ctx, monkeypatch):
    monkeypatch.setattr(app_mod, "list_input_devices", lambda: ())

    class Cancelled:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return 0

    monkeypatch.setattr(app_mod, "SettingsDialog", Cancelled)
    app_mod._open_settings(ctx)
    assert ctx.settings.hotkey == "ctrl+alt+space"


def test_quit_hides_tray_and_unregisters_hotkey(ctx):
    ctx.tray.show()
    unregistered = []
    ctx.hotkey.unregister = lambda: unregistered.append(True)
    app_mod._quit(ctx)
    assert unregistered == [True] and not ctx.tray.isVisible()


def test_run_toggle_returns_error_when_not_running(monkeypatch):
    monkeypatch.setattr(app_mod, "send_command", lambda *a, **k: False)
    assert app_mod._run_toggle() == 1


def test_run_toggle_sends_toggle_message(monkeypatch):
    sent = {}

    def fake_send(name, message):
        sent.update(name=name, message=message)
        return True

    monkeypatch.setattr(app_mod, "send_command", fake_send)
    assert app_mod._run_toggle() == 0
    assert sent["message"] == app_mod.TOGGLE_MESSAGE
    assert sent["name"] == app_mod.DEFAULT_NAME


def test_apply_hotkey_falls_back_to_cli_label_off_windows(ctx, monkeypatch):
    monkeypatch.setattr(app_mod.sys, "platform", "linux")
    notifications = []
    ctx.tray.notify = lambda *a, **k: notifications.append(a)
    app_mod._apply_hotkey(ctx)
    assert notifications == []  # Linux'ta hata bildirimi gösterilmez
    assert "dikte --toggle" in ctx.tray.toolTip()


def test_apply_hotkey_notifies_on_windows_failure(ctx, monkeypatch):
    monkeypatch.setattr(app_mod.sys, "platform", "win32")
    ctx.hotkey.register = lambda _spec: False
    notifications = []
    ctx.tray.notify = lambda *a, **k: notifications.append(a)
    app_mod._apply_hotkey(ctx)
    assert len(notifications) == 1


def test_downgrade_notice_is_shown_once_ready(ctx):
    notifications = []
    ctx.tray.notify = lambda *a, **k: notifications.append(a[1])
    ctx.stt._downgraded = True
    ctx.stt._compute_type = "float32"
    ctx.controller.ready_changed.emit(True)
    assert len(notifications) == 1 and "float32" in notifications[0]


def test_no_notice_when_compute_type_is_honoured(ctx):
    notifications = []
    ctx.tray.notify = lambda *a, **k: notifications.append(a)
    ctx.controller.ready_changed.emit(True)
    assert notifications == []


def test_make_llm_skips_provider_when_disabled():
    s = Settings()
    disabled = s.model_copy(update={"llm": s.llm.model_copy(update={"enabled": False})})
    assert app_mod._make_llm(disabled).name == "none"


def test_open_settings_rebuilds_llm_without_restart(ctx, monkeypatch):
    monkeypatch.setattr(app_mod, "save_settings", lambda s: None)
    monkeypatch.setattr(app_mod, "set_autostart", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "list_input_devices", lambda: ())
    restarts = []
    monkeypatch.setattr(
        app_mod.QMessageBox, "information", staticmethod(lambda *a, **k: restarts.append(a))
    )

    class FakeDialog:
        def __init__(self, settings, devices, parent=None):
            self._settings = settings

        def exec(self):
            return 1

        def result_settings(self):
            s = self._settings
            return s.model_copy(update={"llm": s.llm.model_copy(update={"enabled": False})})

    monkeypatch.setattr(app_mod, "SettingsDialog", FakeDialog)
    app_mod._open_settings(ctx)
    assert ctx.controller.llm_enabled is False
    assert ctx.controller._llm.name == "none"
    assert restarts == []  # LLM değişikliği yeniden başlatma istemez
    assert not ctx.window.translate_btn.isEnabled()


def _escape_shortcut(window):
    from PySide6.QtGui import QKeySequence, QShortcut

    for sc in window.findChildren(QShortcut):
        if sc.key() == QKeySequence(Qt.Key_Escape):
            return sc
    raise AssertionError("Esc kısayolu bulunamadı")


def test_escape_shortcut_cancels(ctx, qtbot):
    ctx.controller.toggle()
    ctx.window.show()
    _escape_shortcut(ctx.window).activated.emit()
    assert ctx.controller.state is DictationState.IDLE


def test_escape_hides_window_when_idle(ctx, qtbot):
    ctx.window.show()
    _escape_shortcut(ctx.window).activated.emit()
    assert not ctx.window.isVisible()


def test_cancel_hotkey_registered_only_while_busy(ctx):
    calls = []
    ctx.cancel_hotkey.register = lambda spec: calls.append(("reg", spec)) or True
    ctx.cancel_hotkey.unregister = lambda: calls.append(("unreg", None))
    ctx.controller.state_changed.emit(DictationState.RECORDING)
    ctx.controller.state_changed.emit(DictationState.IDLE)
    assert calls == [("reg", "escape"), ("unreg", None)]


def test_overlay_and_tray_cancel_reach_controller(ctx):
    ctx.controller.toggle()
    ctx.overlay.cancel_requested.emit()
    assert ctx.controller.state is DictationState.IDLE
    ctx.controller.toggle()
    ctx.tray.cancel_requested.emit()
    assert ctx.controller.state is DictationState.IDLE


def test_cancel_hotkey_uses_separate_id(ctx):
    from dikte.platform.hotkey import HOTKEY_ID

    assert ctx.hotkey._id == HOTKEY_ID and ctx.cancel_hotkey._id != HOTKEY_ID
