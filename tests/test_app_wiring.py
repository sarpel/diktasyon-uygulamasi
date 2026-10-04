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


class _FakeSignal:
    """Sahte ayarlar diyaloglarının `health_requested` sinyali (bağlanır, hiç yayılmaz)."""

    def connect(self, *_a, **_k):
        return None


@pytest.fixture
def ctx(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod.paths, "history_path", lambda: tmp_path / "history.jsonl")
    monkeypatch.setattr(app_mod.paths, "failed_audio_path", lambda: tmp_path / "failed.wav")
    c = app_mod.build_app(Settings())
    for w in (c.window, c.overlay):
        qtbot.addWidget(w)
    return c


def test_build_app_returns_wired_context(ctx):
    assert ctx.controller.state is DictationState.IDLE
    assert ctx.window._controller is ctx.controller
    assert "Ctrl+Alt+Space" in ctx.tray.toolTip()


def test_build_app_creates_mode_hotkeys(ctx):
    from dikte.platform.hotkey import GlobalHotkey

    assert isinstance(ctx.hotkey_translate, GlobalHotkey)
    assert isinstance(ctx.hotkey_prompt, GlobalHotkey)
    assert ctx.hotkey_translate._id != ctx.hotkey._id != ctx.hotkey_prompt._id


def test_partial_text_reaches_overlay(ctx):
    ctx.controller.partial_text.emit("kısmi metin")
    assert ctx.overlay._partial.text() == "kısmi metin"


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
        health_requested = _FakeSignal()

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


def test_open_settings_model_change_triggers_reload(ctx, monkeypatch):
    monkeypatch.setattr(app_mod, "save_settings", lambda s: None)
    monkeypatch.setattr(app_mod, "set_autostart", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "list_input_devices", lambda: ())
    informed = []
    monkeypatch.setattr(
        app_mod.QMessageBox, "information", staticmethod(lambda *a, **k: informed.append(a))
    )
    warmed = []
    monkeypatch.setattr(ctx.controller, "warm_up", lambda: warmed.append(True))

    class FakeDialog:
        health_requested = _FakeSignal()

        def __init__(self, settings, devices, parent=None):
            self._settings = settings

        def exec(self):
            return 1  # QDialog.DialogCode.Accepted

        def result_settings(self):
            return self._settings.model_copy(
                update={"stt": self._settings.stt.model_copy(update={"model": "small"})}
            )

    monkeypatch.setattr(app_mod, "SettingsDialog", FakeDialog)
    app_mod._open_settings(ctx)
    assert warmed == [True]
    assert informed == []


def test_open_settings_cancelled_changes_nothing(ctx, monkeypatch):
    monkeypatch.setattr(app_mod, "list_input_devices", lambda: ())

    class Cancelled:
        health_requested = _FakeSignal()

        def __init__(self, *a, **k):
            pass

        def exec(self):
            return 0

    monkeypatch.setattr(app_mod, "SettingsDialog", Cancelled)
    app_mod._open_settings(ctx)
    assert ctx.settings.hotkey == "ctrl+alt+space"


def test_quit_hides_tray_and_asks_app_to_quit(ctx, monkeypatch):
    """Temizlik aboutToQuit'e bağlı _shutdown'dadır; _quit yalnızca tepsiyi gizleyip çıkar."""
    from types import SimpleNamespace

    ctx.tray.show()
    quits = []
    fake_app = SimpleNamespace(quit=lambda: quits.append(True))
    monkeypatch.setattr(app_mod, "QApplication", SimpleNamespace(instance=lambda: fake_app))
    app_mod._quit(ctx)
    assert quits == [True] and not ctx.tray.isVisible()


def _record_shutdown_calls(ctx, monkeypatch):
    calls = []
    hotkeys = (
        ctx.hotkey,
        ctx.cancel_hotkey,
        ctx.hotkey_translate,
        ctx.hotkey_prompt,
        ctx.hotkey_paste_last,
    )
    for hk in hotkeys:
        monkeypatch.setattr(hk, "unregister", lambda: calls.append("unregister"))
    monkeypatch.setattr(ctx.controller, "cancel", lambda: calls.append("cancel"))
    monkeypatch.setattr(ctx.recorder, "stop", lambda: calls.append("stop"))
    return calls


def test_shutdown_unregisters_hotkeys_cancels_and_stops_recorder(ctx, monkeypatch):
    calls = _record_shutdown_calls(ctx, monkeypatch)
    app_mod._shutdown(ctx)
    assert calls.count("unregister") == 5
    assert calls.count("cancel") == 1 and calls.count("stop") == 1


def test_shutdown_is_idempotent(ctx, monkeypatch):
    calls = _record_shutdown_calls(ctx, monkeypatch)
    app_mod._shutdown(ctx)
    app_mod._shutdown(ctx)
    assert calls.count("cancel") == 1 and calls.count("unregister") == 5


def test_shutdown_waits_for_running_background_jobs(ctx, monkeypatch):
    import time

    from dikte.core.workers import run_in_pool

    _record_shutdown_calls(ctx, monkeypatch)
    finished = []
    jobs = [
        run_in_pool(
            lambda: (time.sleep(0.2), finished.append("global")),
            lambda _r: None,
            lambda _e: None,
        )
    ]
    ctx.media_pool = app_mod.QThreadPool()
    jobs.append(
        run_in_pool(
            lambda: (time.sleep(0.2), finished.append("media")),
            lambda _r: None,
            lambda _e: None,
            ctx.media_pool,
        )
    )
    app_mod._shutdown(ctx)
    assert sorted(finished) == ["global", "media"]


def test_shutdown_runs_when_application_is_about_to_quit(ctx, monkeypatch):
    """Oturum kapatma/Windows kapanışı _quit'ten geçmez; temizlik aboutToQuit'e bağlı."""
    from PySide6.QtCore import QObject, Signal

    class FakeApp(QObject):
        aboutToQuit = Signal()

    calls = _record_shutdown_calls(ctx, monkeypatch)
    fake_app = FakeApp()
    app_mod._install_shutdown(ctx, fake_app)
    fake_app.aboutToQuit.emit()
    assert "cancel" in calls and ctx.shut_down


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


def test_hotkey_routes_to_toggle_when_ptt_off(ctx):
    ctx.settings = ctx.settings.model_copy(update={"push_to_talk": False})
    app_mod._on_hotkey(ctx)
    assert ctx.controller.state is DictationState.RECORDING


def test_hotkey_arms_detector_on_windows(ctx, monkeypatch):
    monkeypatch.setattr(app_mod.sys, "platform", "win32")
    ctx.settings = ctx.settings.model_copy(update={"push_to_talk": True})
    armed = []
    ctx.hold.arm = lambda vk: armed.append(vk)
    app_mod._on_hotkey(ctx)
    assert armed == [app_mod.parse_hotkey(ctx.settings.hotkey).vk]


def test_translate_hotkey_toggles_in_translate_mode_when_ptt_off(ctx):
    ctx.settings = ctx.settings.model_copy(
        update={"push_to_talk": False, "hotkey_translate": "ctrl+alt+t"}
    )
    app_mod._on_hotkey(ctx, "translate")
    assert ctx.controller.state is DictationState.RECORDING
    assert ctx.controller.session.mode == "translate"


def test_translate_hotkey_arms_detector_with_own_vk_on_windows(ctx, monkeypatch):
    monkeypatch.setattr(app_mod.sys, "platform", "win32")
    ctx.settings = ctx.settings.model_copy(
        update={"push_to_talk": True, "hotkey_translate": "ctrl+alt+t"}
    )
    armed = []
    ctx.hold.arm = lambda vk: armed.append(vk)
    app_mod._on_hotkey(ctx, "translate")
    assert armed == [app_mod.parse_hotkey("ctrl+alt+t").vk]
    assert ctx.hold_mode == "translate"


def test_hotkey_resolves_matching_profile_and_overrides_mode(ctx, monkeypatch):
    from dikte.config import AppProfile

    profile = AppProfile(name="Kod", match="code", mode="translate")
    ctx.settings = ctx.settings.model_copy(update={"push_to_talk": False, "profiles": (profile,)})
    monkeypatch.setattr(app_mod, "foreground_process_name", lambda: "Code.exe")
    app_mod._on_hotkey(ctx)
    assert ctx.active_profile is profile
    assert ctx.controller.session.mode == "translate"


def test_hotkey_no_matching_profile_leaves_active_profile_none(ctx, monkeypatch):
    ctx.settings = ctx.settings.model_copy(update={"push_to_talk": False})
    monkeypatch.setattr(app_mod, "foreground_process_name", lambda: "explorer.exe")
    app_mod._on_hotkey(ctx)
    assert ctx.active_profile is None


def test_apply_hotkey_falls_back_to_cli_label_off_windows(ctx, monkeypatch):
    monkeypatch.setattr(app_mod.sys, "platform", "linux")
    notifications = []
    ctx.tray.notify = lambda *a, **k: notifications.append(a)
    app_mod._apply_hotkey(ctx)
    assert notifications == []  # Linux'ta hata bildirimi gösterilmez
    assert "dikte --toggle" in ctx.tray.toolTip()


def test_apply_hotkey_notifies_on_windows_failure(ctx, monkeypatch):
    monkeypatch.setattr(app_mod.sys, "platform", "win32")
    ctx.hotkey.register = lambda _spec, **kw: False
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
        health_requested = _FakeSignal()

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
        if sc.key() == QKeySequence(Qt.Key.Key_Escape):
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
    ctx.cancel_hotkey.register = lambda spec, **kw: calls.append(("reg", spec, kw)) or True
    ctx.cancel_hotkey.unregister = lambda: calls.append(("unreg", None))
    ctx.controller.state_changed.emit(DictationState.RECORDING)
    ctx.controller.state_changed.emit(DictationState.IDLE)
    assert calls == [("reg", "escape", {"allow_bare": True}), ("unreg", None)]


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


def test_result_ready_copies_to_clipboard_and_pastes(ctx, monkeypatch):
    from PySide6.QtWidgets import QApplication

    pasted = []
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: pasted.append(ids) or True)
    ctx.controller.result_ready.emit("Merhaba.")
    assert QApplication.clipboard().text() == "Merhaba."
    assert len(pasted) == 1


def test_file_sourced_result_is_copied_but_not_pasted(ctx, monkeypatch):
    from PySide6.QtWidgets import QApplication

    ctx.controller._session = Session(source_path="/tmp/a.wav")
    pasted = []
    monkeypatch.setattr(app_mod, "paste_active_window", lambda *a, **k: pasted.append(1) or True)
    ctx.controller.result_ready.emit("Dosyadan gelen metin.")
    assert QApplication.clipboard().text() == "Dosyadan gelen metin."
    assert pasted == []


def test_window_file_requested_reaches_controller_transcribe_file(ctx):
    ctx.window.file_requested.emit("/tmp/a.wav")
    assert ctx.controller.state is DictationState.TRANSCRIBING
    assert ctx.controller.session.source_path == "/tmp/a.wav"


def test_result_ready_respects_auto_paste_off(ctx, monkeypatch):
    ctx.settings = ctx.settings.model_copy(update={"auto_paste": False})
    pasted = []
    monkeypatch.setattr(app_mod, "paste_active_window", lambda *a, **k: pasted.append(1))
    ctx.controller.result_ready.emit("x")
    assert pasted == []


def test_result_ready_respects_auto_copy_off(ctx, monkeypatch):
    from PySide6.QtWidgets import QApplication

    QApplication.clipboard().setText("eski")
    ctx.settings = ctx.settings.model_copy(update={"auto_copy": False})
    monkeypatch.setattr(app_mod, "paste_active_window", lambda *a, **k: True)
    ctx.controller.result_ready.emit("yeni")
    assert QApplication.clipboard().text() == "eski"


def _record_timers(monkeypatch):
    from types import SimpleNamespace

    scheduled = []
    monkeypatch.setattr(
        app_mod, "QTimer", SimpleNamespace(singleShot=lambda ms, fn: scheduled.append((ms, fn)))
    )
    return scheduled


def test_paste_still_happens_when_raise_on_result_activates_window(ctx, qtbot, monkeypatch):
    """result_ready, RESULT durumuna geçiş penceresini aktive etmeden önce işlenmeli;
    aksi halde yapıştırma hedefi kaybolur."""
    ctx.settings = ctx.settings.model_copy(update={"raise_window_on_result": True})
    pasted = []
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: pasted.append(ids) or True)
    ctx.controller.state_changed.emit(DictationState.RESULT)
    ctx.controller.result_ready.emit("Merhaba.")
    assert len(pasted) == 1


def test_raise_on_result_waits_until_sent_paste_lands(ctx, monkeypatch):
    """SendInput Ctrl+V'yi eşzamansız kuyruğa koyar; pencere hemen öne gelirse yapıştırma
    Dikte'nin kendi editörüne düşer (metin ikilenir ve geçmişe kaydedilir)."""
    ctx.settings = ctx.settings.model_copy(update={"raise_window_on_result": True})
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: True)
    scheduled = _record_timers(monkeypatch)
    ctx.controller.result_ready.emit("Merhaba.")
    assert scheduled == [(app_mod.restore_delay_ms("Merhaba."), ctx.window.activate_result)]


def test_raise_on_result_is_immediate_when_nothing_was_pasted(ctx, monkeypatch):
    ctx.settings = ctx.settings.model_copy(
        update={"raise_window_on_result": True, "auto_paste": False}
    )
    scheduled = _record_timers(monkeypatch)
    ctx.controller.result_ready.emit("Merhaba.")
    assert scheduled == [(0, ctx.window.activate_result)]


def test_window_not_raised_when_setting_off(ctx, monkeypatch):
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: True)
    scheduled = _record_timers(monkeypatch)
    ctx.controller.result_ready.emit("Merhaba.")
    assert scheduled == []


def test_restore_clipboard_after_paste(ctx, monkeypatch, qtbot):
    from PySide6.QtWidgets import QApplication

    ctx.settings = ctx.settings.model_copy(update={"restore_clipboard": True})
    QApplication.clipboard().setText("eski")
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: True)
    app_mod._on_result_ready(ctx, "yeni")
    assert QApplication.clipboard().text() == "yeni"
    qtbot.waitUntil(lambda: QApplication.clipboard().text() == "eski", timeout=2000)


def test_restore_clipboard_preserves_image_not_just_text(ctx, monkeypatch, qtbot):
    """F: restore_clipboard yalnızca metni koruyordu; panodaki bir resim dikte sonrası
    geri yükleme sırasında sessizce kayboluyordu."""
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    ctx.settings = ctx.settings.model_copy(update={"restore_clipboard": True})
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(0xFF00FF)
    QApplication.clipboard().setImage(image)
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: True)
    app_mod._on_result_ready(ctx, "yeni")
    assert QApplication.clipboard().text() == "yeni"
    qtbot.waitUntil(lambda: not QApplication.clipboard().image().isNull(), timeout=2000)
    restored = QApplication.clipboard().image()
    assert restored.size() == image.size()


def test_clipboard_not_restored_when_paste_skipped(ctx, monkeypatch, qtbot):
    from PySide6.QtWidgets import QApplication

    ctx.settings = ctx.settings.model_copy(update={"restore_clipboard": True})
    QApplication.clipboard().setText("eski")
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: False)
    app_mod._on_result_ready(ctx, "yeni")
    qtbot.wait(400)
    assert QApplication.clipboard().text() == "yeni"


def test_result_ready_uses_profile_paste_combo(ctx, monkeypatch):
    from dikte.config import AppProfile

    ctx.controller._active_profile = AppProfile(name="Terminal", match="wt", paste="ctrl+shift+v")
    combos = []
    monkeypatch.setattr(
        app_mod, "paste_active_window", lambda ids, **k: combos.append(k.get("combo")) or True
    )
    app_mod._on_result_ready(ctx, "Merhaba.")
    assert combos == ["ctrl+shift+v"]


def test_result_ready_uses_type_when_profile_paste_is_type(ctx, monkeypatch):
    from dikte.config import AppProfile

    ctx.controller._active_profile = AppProfile(name="Kod", match="code", paste="type")
    typed = []
    pasted = []
    monkeypatch.setattr(app_mod, "type_unicode_text", lambda text: typed.append(text) or True)
    monkeypatch.setattr(app_mod, "paste_active_window", lambda *a, **k: pasted.append(1) or True)
    app_mod._on_result_ready(ctx, "Merhaba.")
    assert typed == ["Merhaba."]
    assert pasted == []


def test_result_ready_appends_profile_trailing(ctx, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from dikte.config import AppProfile

    ctx.controller._active_profile = AppProfile(name="Terminal", match="wt", trailing="\n")
    monkeypatch.setattr(app_mod, "paste_active_window", lambda *a, **k: True)
    app_mod._on_result_ready(ctx, "Merhaba.")
    assert QApplication.clipboard().text() == "Merhaba.\n"


def test_history_panel_refreshes_on_result(ctx):
    ctx.controller._update_session(raw_text="a", corrected_text="A.")
    ctx.controller.state_changed.emit(DictationState.RESULT)
    assert ctx.window.history_panel.list_widget.count() == 1


def test_history_delete_flows_to_storage(ctx):
    ctx.controller._update_session(corrected_text="A.")
    ctx.controller.state_changed.emit(DictationState.RESULT)
    sid = ctx.history.load()[0].id
    ctx.window.history_panel.delete_requested.emit(sid)
    assert ctx.history.load() == ()
    assert ctx.window.history_panel.list_widget.count() == 0


def test_history_clear_flows_to_storage(ctx):
    ctx.controller._update_session(corrected_text="A.")
    ctx.controller.state_changed.emit(DictationState.RESULT)
    ctx.window.history_panel.clear_requested.emit()
    assert ctx.history.load() == ()


def test_result_state_updates_tray_recent(ctx):
    ctx.controller._update_session(raw_text="a", corrected_text="A.")
    ctx.controller.state_changed.emit(DictationState.RESULT)
    assert len(ctx.tray._recent_menu.actions()) == 1


def test_tray_copy_requested_writes_to_clipboard(ctx):
    from PySide6.QtWidgets import QApplication

    ctx.tray.copy_requested.emit("panoya gidecek metin")
    assert QApplication.clipboard().text() == "panoya gidecek metin"


def test_clipboard_exclude_history_reaches_all_copy_paths(ctx, monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_mod, "copy_text", lambda text, *, exclude_history: calls.append(exclude_history)
    )
    ctx.settings = ctx.settings.model_copy(update={"clipboard_exclude_history": False})
    ctx.tray.copy_requested.emit("x")
    assert calls == [False]
    w = ctx.window
    w.set_clipboard_exclude_history(False)
    panes = (w.raw_pane, w.corrected_pane, w.output_pane)
    assert not any(p.exclude_history for p in panes)
    assert w.history_panel.exclude_history is False


def test_export_requested_writes_file(ctx, tmp_path):
    ctx.controller._update_session(raw_text="a", corrected_text="A.")
    ctx.controller.state_changed.emit(DictationState.RESULT)
    out = tmp_path / "gecmis.md"
    ctx.window.history_panel.export_requested.emit(str(out))
    assert out.exists()
    assert "A." in out.read_text(encoding="utf-8")


def test_export_requested_writes_plain_text_for_txt_extension(ctx, tmp_path):
    ctx.controller._update_session(raw_text="a", corrected_text="A.")
    ctx.controller.state_changed.emit(DictationState.RESULT)
    out = tmp_path / "gecmis.txt"
    ctx.window.history_panel.export_requested.emit(str(out))
    content = out.read_text(encoding="utf-8")
    assert content.startswith("[") and "A." in content
    assert "# Dikte" not in content


def test_export_failure_notifies_tray_instead_of_crashing(ctx, monkeypatch):
    notified = []
    monkeypatch.setattr(ctx.tray, "notify", lambda *a, **k: notified.append(a))
    monkeypatch.setattr(
        app_mod.Path, "write_text", lambda *a, **k: (_ for _ in ()).throw(OSError("dolu"))
    )
    ctx.window.history_panel.export_requested.emit("/gecersiz/yol/x.md")
    assert notified


def test_history_selection_loads_into_window(ctx):
    from dikte.core.state import Session

    ctx.window.history_panel.session_selected.emit(Session(corrected_text="Eski metin"))
    assert ctx.window.corrected_pane.text() == "Eski metin"


def test_text_edited_reaches_controller_apply_edit(ctx):
    ctx.controller._update_session(raw_text="a", corrected_text="A.")
    ctx.controller._state = DictationState.RESULT
    ctx.window.text_edited.emit(ctx.controller.session.id, "A düzenlendi.")
    assert ctx.controller.session.corrected_text == "A düzenlendi."


def test_text_edited_for_history_session_does_not_touch_live_session(ctx):
    from dikte.core.state import Session

    ctx.controller._update_session(raw_text="a", corrected_text="A.")
    ctx.controller._state = DictationState.RESULT
    ctx.history.append(Session(id="old-1", raw_text="eski", corrected_text="Eski."))
    ctx.window.text_edited.emit("old-1", "Eski düzenlendi.")
    assert ctx.controller.session.corrected_text == "A."
    assert [s.corrected_text for s in ctx.history.load() if s.id == "old-1"] == ["Eski düzenlendi."]


def test_session_update_while_result_updates_history(ctx):
    ctx.controller._update_session(raw_text="a", corrected_text="A.")
    ctx.controller.state_changed.emit(DictationState.RESULT)
    ctx.controller._state = DictationState.RESULT
    ctx.controller._update_session(corrected_text="A düzenlendi.")
    assert [s.corrected_text for s in ctx.history.load()] == ["A düzenlendi."]


def test_session_update_before_result_does_not_touch_history(ctx):
    ctx.controller._update_session(raw_text="a", corrected_text="A.")
    assert ctx.history.load() == ()


def test_edit_learned_shows_dictionary_suggestion(ctx):
    from dikte.llm.diff import Change

    ctx.controller.edit_learned.emit((Change("çuk", "çok", "değiştirildi"),))
    assert ctx.window.suggest_bar.isVisible() or ctx.window._pending_suggestion == ("çuk", "çok")


def test_edit_learned_ignored_when_suggest_dictionary_off(ctx):
    from dikte.llm.diff import Change

    ctx.settings = ctx.settings.model_copy(update={"suggest_dictionary": False})
    ctx.controller.edit_learned.emit((Change("çuk", "çok", "değiştirildi"),))
    assert ctx.window._pending_suggestion is None


def test_add_dictionary_entry_saves_and_updates_settings(ctx, monkeypatch):
    saved = []
    monkeypatch.setattr(app_mod, "save_settings", saved.append)
    ctx.window.dictionary_add_requested.emit("çuk", "çok")
    assert ctx.settings.dictionary.entries[-1].term == "çok"
    assert ctx.settings.dictionary.entries[-1].wrong == ("çuk",)
    assert saved and saved[0].dictionary.entries[-1].term == "çok"


def test_repaste_hides_window_and_re_delivers_text(ctx, monkeypatch, qtbot):
    ctx.window.show()
    delivered = []
    monkeypatch.setattr(app_mod, "_on_result_ready", lambda c, t, **k: delivered.append(t))
    ctx.window.repaste_requested.emit("yeniden yapıştırılan metin")
    assert not ctx.window.isVisible()
    qtbot.waitUntil(lambda: delivered == ["yeniden yapıştırılan metin"], timeout=1000)


def test_status_info_set_when_ready(ctx):
    ctx.stt._compute_type = "float16"
    ctx.controller.ready_changed.emit(True)
    assert "float16" in ctx.window.status_info.text()


def test_low_vram_shows_status_bar_warning(ctx, monkeypatch, qtbot):
    from dikte.platform.gpu_info import VramInfo

    monkeypatch.setattr(app_mod, "query_vram", lambda: VramInfo(7500, 8192))
    app_mod._refresh_status_info(ctx)
    # nvidia-smi arka planda sorgulanır (GUI iş parçacığı bloke olmaz)
    qtbot.waitUntil(
        lambda: "Boş VRAM düşük" in ctx.window.statusBar().currentMessage(), timeout=2000
    )


def test_sufficient_vram_shows_no_warning(ctx, monkeypatch):
    from dikte.platform.gpu_info import VramInfo

    monkeypatch.setattr(app_mod, "query_vram", lambda: VramInfo(1000, 8192))
    app_mod._refresh_status_info(ctx)
    assert "Boş VRAM düşük" not in ctx.window.statusBar().currentMessage()


def test_unknown_vram_shows_no_warning(ctx, monkeypatch):
    monkeypatch.setattr(app_mod, "query_vram", lambda: None)
    app_mod._refresh_status_info(ctx)
    assert "Boş VRAM düşük" not in ctx.window.statusBar().currentMessage()


def test_status_info_shows_actually_loaded_model_not_pending_setting(ctx):
    ctx.controller.ready_changed.emit(True)
    assert ctx.stt.active_model in ctx.window.status_info.text()
    ctx.settings = ctx.settings.model_copy(
        update={
            "stt": ctx.settings.stt.model_copy(update={"model": "farkli-model-henuz-yuklenmedi"})
        }
    )
    ctx.controller.ready_changed.emit(True)
    assert "farkli-model-henuz-yuklenmedi" not in ctx.window.status_info.text()


def test_window_toolbar_reaches_controller(ctx):
    ctx.window.record_action.trigger()
    assert ctx.controller.state is DictationState.RECORDING
    ctx.window.cancel_action.trigger()
    assert ctx.controller.state is DictationState.IDLE


def test_invalid_hotkey_in_config_falls_back(monkeypatch, qtbot, tmp_path):
    from dikte.config import Settings as S

    monkeypatch.setattr(app_mod.paths, "history_path", lambda: tmp_path / "h.jsonl")
    ctx = app_mod.build_app(S(hotkey="ctrl+"))
    for w in (ctx.window, ctx.overlay):
        qtbot.addWidget(w)
    assert ctx.settings.hotkey == S().hotkey


def test_valid_hotkey_is_left_alone():
    from dikte.config import Settings as S

    s = S(hotkey="ctrl+shift+d")
    assert app_mod._safe_hotkey(s) is s


def test_error_shows_on_overlay(ctx):
    ctx.controller.error.emit("Konuşma algılanmadı")
    assert ctx.overlay.isVisible()
    assert "Konuşma" in ctx.overlay._status.text()


def test_stt_model_load_error_shows_health_dialog(ctx, monkeypatch, qtbot):
    from dikte.core.health import HealthItem

    fake_items = (
        HealthItem("GPU", True, "1 CUDA aygıtı", ""),
        HealthItem("Whisper modeli", False, "indirilmemiş", "indirin"),
        HealthItem("LLM", True, "kapalı", ""),
    )
    monkeypatch.setattr(app_mod, "check_health", lambda *a, **k: fake_items)
    assert ctx.health_dialog is None
    ctx.controller.error.emit("STT modeli yüklenemedi: dosya bulunamadı")
    # check_health artık arka planda (QThreadPool) çalışıyor; GUI iş parçacığı bloke olmasın diye.
    qtbot.waitUntil(lambda: ctx.health_dialog is not None, timeout=3000)
    dialog = ctx.health_dialog
    assert dialog is not None
    assert len(dialog._labels) == 3


def test_unrelated_error_does_not_show_health_dialog(ctx):
    ctx.controller.error.emit("Konuşma algılanmadı")
    assert ctx.health_dialog is None


def test_history_write_failure_notifies_user(ctx, monkeypatch):
    """Geçmiş yazılamazsa uygulama çökmez; tepsi bildirimiyle uyarır."""
    from dikte.core.history import HistoryError

    notified = []
    monkeypatch.setattr(
        ctx.tray, "notify", lambda title, msg, critical=False: notified.append((msg, critical))
    )

    def boom(_session):
        raise HistoryError("Geçmiş kaydedilemedi (…): disk dolu.")

    monkeypatch.setattr(ctx.history, "append", boom)
    ctx.controller.state_changed.emit(DictationState.RESULT)
    assert notified and notified[-1][1] is True and "Geçmiş kaydedilemedi" in notified[-1][0]


# ---- inceleme düzeltmeleri


def test_ipc_toggle_applies_matching_profile(ctx, monkeypatch):
    from dikte.config import AppProfile

    profile = AppProfile(name="Terminal", match="gnome-terminal-server", mode="prompt")
    ctx.settings = ctx.settings.model_copy(update={"profiles": (profile,)})
    monkeypatch.setattr(app_mod, "foreground_process_name", lambda: "gnome-terminal-server")
    app_mod._on_ipc_toggle(ctx, "correct")
    assert ctx.controller.state is DictationState.RECORDING
    assert ctx.controller.active_profile is profile
    assert ctx.controller.session.mode == "prompt"


def test_ipc_start_applies_matching_profile(ctx, monkeypatch):
    from dikte.config import AppProfile

    profile = AppProfile(name="Kod", match="code", mode="translate")
    ctx.settings = ctx.settings.model_copy(update={"profiles": (profile,)})
    monkeypatch.setattr(app_mod, "foreground_process_name", lambda: "code")
    app_mod._on_ipc_start(ctx, "correct")
    assert ctx.controller.session.mode == "translate"


def test_export_history_reports_unreadable_history(ctx, tmp_path, monkeypatch):
    from dikte.core.history import HistoryError

    def boom():
        raise HistoryError("Geçmiş okunamadı")

    notes = []
    monkeypatch.setattr(ctx.history, "load", boom)
    monkeypatch.setattr(ctx.tray, "notify", lambda *a, **k: notes.append(a))
    out = tmp_path / "out.md"
    app_mod._export_history(ctx, str(out))
    assert not out.exists()
    assert notes and "Geçmiş okunamadı" in notes[0][1]


def test_model_change_while_busy_reloads_when_idle(ctx, monkeypatch):
    monkeypatch.setattr(app_mod, "save_settings", lambda s: None)
    monkeypatch.setattr(app_mod, "set_autostart", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "list_input_devices", lambda: ())
    informed = []
    monkeypatch.setattr(
        app_mod.QMessageBox, "information", staticmethod(lambda *a, **k: informed.append(a))
    )
    warmed = []
    monkeypatch.setattr(ctx.controller, "warm_up", lambda: warmed.append(True))
    monkeypatch.setattr(
        type(ctx.controller), "state", property(lambda self: DictationState.TRANSCRIBING)
    )

    class FakeDialog:
        health_requested = _FakeSignal()

        def __init__(self, settings, devices, parent=None):
            self._settings = settings

        def exec(self):
            return 1

        def result_settings(self):
            return self._settings.model_copy(
                update={"stt": self._settings.stt.model_copy(update={"model": "small"})}
            )

    monkeypatch.setattr(app_mod, "SettingsDialog", FakeDialog)
    app_mod._open_settings(ctx)
    assert warmed == [] and "otomatik" in informed[0][2]
    ctx.controller.state_changed.emit(DictationState.CORRECTING)
    assert warmed == []
    ctx.controller.state_changed.emit(DictationState.RESULT)
    ctx.controller.state_changed.emit(DictationState.IDLE)
    assert warmed == [True]


def test_config_issues_are_reported(ctx, monkeypatch):
    notes = []
    monkeypatch.setattr(ctx.tray, "notify", lambda *a, **k: notes.append(a))
    app_mod._notify_config_issues(ctx, ("stt.beam_size", "llm.provider"))
    assert "stt.beam_size, llm.provider" in notes[0][1]
    app_mod._notify_config_issues(ctx, ("*",))
    assert "okunamadı" in notes[1][1] and ".bak" in notes[1][1]


def test_unreadable_config_notice_does_not_point_to_backup(ctx, monkeypatch):
    from dikte.config import UNREADABLE

    notes = []
    monkeypatch.setattr(ctx.tray, "notify", lambda *a, **k: notes.append(a))
    app_mod._notify_config_issues(ctx, UNREADABLE)
    assert "okunamadı" in notes[0][1] and ".bak" not in notes[0][1]


def test_sanitized_hotkeys_include_paste_last():
    before = Settings(hotkey_paste_last="bozuk+++")
    after = before.model_copy(update={"hotkey_paste_last": ""})
    assert app_mod._sanitized_hotkeys(before, after) == ("hotkey_paste_last",)
    assert app_mod._sanitized_hotkeys(before, before) == ()


def test_restore_clipboard_skipped_when_user_copied_meanwhile(ctx, monkeypatch, qtbot):
    from PySide6.QtWidgets import QApplication

    ctx.settings = ctx.settings.model_copy(update={"restore_clipboard": True})
    QApplication.clipboard().setText("eski")
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: True)
    app_mod._on_result_ready(ctx, "yeni")
    QApplication.clipboard().setText("kullanıcının yeni kopyası")
    qtbot.wait(app_mod.restore_delay_ms("yeni") + 200)
    assert QApplication.clipboard().text() == "kullanıcının yeni kopyası"


def test_result_uses_history_excluding_mime(ctx, monkeypatch):
    built = []

    def fake_build(text, *, exclude_history):
        built.append(exclude_history)
        from dikte.platform.clipboard import new_mime_data

        m = new_mime_data()  # panoda kalır: C++ nesnesi olmalı (kapanışta çökme)
        m.setText(text)
        return m

    monkeypatch.setattr(app_mod, "build_mime", fake_build)
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: True)
    app_mod._on_result_ready(ctx, "metin")
    assert built == [True]


class _FakeMedia:
    def __init__(self):
        self.calls = []

    def pause(self):
        self.calls.append("pause")

    def resume(self):
        self.calls.append("resume")


def test_media_paused_during_recording_and_resumed_after(ctx, qtbot):
    ctx.settings = ctx.settings.model_copy(update={"pause_media": True})
    ctx.media = _FakeMedia()
    ctx.controller.state_changed.emit(DictationState.RECORDING)
    ctx.controller.state_changed.emit(DictationState.RECORDING)
    ctx.controller.state_changed.emit(DictationState.TRANSCRIBING)
    ctx.controller.state_changed.emit(DictationState.RESULT)
    qtbot.waitUntil(lambda: ctx.media.calls == ["pause", "resume"], timeout=2000)


def test_media_untouched_when_setting_off(ctx, qtbot):
    ctx.media = _FakeMedia()
    ctx.controller.state_changed.emit(DictationState.RECORDING)
    ctx.controller.state_changed.emit(DictationState.IDLE)
    qtbot.wait(100)
    assert ctx.media.calls == []


def test_autostart_failure_is_reported(ctx, monkeypatch):
    from dikte.platform.autostart import AutostartError

    def boom(enabled):
        raise AutostartError("Otomatik başlatma ayarlanamadı")

    notes = []
    monkeypatch.setattr(app_mod, "set_autostart", boom)
    monkeypatch.setattr(ctx.tray, "notify", lambda *a, **k: notes.append(a))
    app_mod._apply_autostart(ctx, True)
    assert "Otomatik başlatma" in notes[0][1]


def test_paste_last_repastes_latest_result(ctx, monkeypatch):
    delivered = []
    monkeypatch.setattr(
        app_mod, "_on_result_ready", lambda c, text, **k: delivered.append((text, k))
    )
    ctx.controller._update_session(raw_text="a", corrected_text="Son metin.")
    ctx.tray.paste_last_requested.emit()
    assert delivered == [("Son metin.", {"force_paste": True})]


def test_paste_last_falls_back_to_history(ctx, monkeypatch):
    delivered = []
    monkeypatch.setattr(app_mod, "_on_result_ready", lambda c, text, **k: delivered.append(text))
    ctx.history.append(Session(raw_text="x", corrected_text="Geçmişteki."))
    app_mod._paste_last(ctx)
    assert delivered == ["Geçmişteki."]


def test_paste_last_without_result_notifies(ctx, monkeypatch):
    notes = []
    monkeypatch.setattr(ctx.tray, "notify", lambda *a, **k: notes.append(a))
    app_mod._paste_last(ctx)
    assert "Yapıştırılacak" in notes[0][1]


def test_overlay_drag_persists_custom_position(ctx, monkeypatch):
    saved = []
    monkeypatch.setattr(app_mod, "save_settings", lambda s: saved.append(s))
    ctx.overlay.moved.emit(120, 340)
    assert ctx.settings.overlay_position == "custom"
    assert ctx.settings.overlay_xy == (120, 340)
    assert saved and saved[0].overlay_xy == (120, 340)


def test_health_dialog_reference_cleared_when_destroyed(ctx, qtbot):
    app_mod._show_health_dialog(ctx, ())
    dialog = ctx.health_dialog
    assert dialog is not None
    dialog.close()
    qtbot.waitUntil(lambda: ctx.health_dialog is None, timeout=2000)
    app_mod._show_health_dialog(ctx, ())  # silinmiş pencereye erişip çökmemeli
    assert ctx.health_dialog is not None
    ctx.health_dialog.close()


def test_model_download_triggers_reload(ctx, monkeypatch):
    warmed = []
    monkeypatch.setattr(ctx.controller, "warm_up", lambda: warmed.append(True))
    app_mod._show_health_dialog(ctx, ())
    assert ctx.health_dialog is not None
    ctx.health_dialog.model_downloaded.emit()
    assert warmed == [True]
    ctx.health_dialog.close()


def test_invalid_paste_last_hotkey_is_disabled():
    s = app_mod._safe_hotkey(Settings(hotkey_paste_last="ctrl+alt+bozuk tuş"))
    assert s.hotkey_paste_last == ""


def test_controller_warning_reaches_overlay(ctx):
    ctx.controller.warning.emit("Mikrofondan ses gelmiyor.")
    assert "Mikrofondan ses gelmiyor." in ctx.overlay._warning.text()


def test_failed_audio_toggles_tray_retry_action(ctx):
    ctx.controller.failed_audio_changed.emit(True)
    assert ctx.tray._retry_action.isEnabled()
    ctx.controller.failed_audio_changed.emit(False)
    assert not ctx.tray._retry_action.isEnabled()


def test_tray_retry_reaches_controller(ctx, tmp_path, qtbot):
    """Saklanmış kayıt yoksa yeniden deneme hata yayınlar; bağlantı controller'a ulaşır."""
    errors = []
    ctx.controller.error.connect(errors.append)
    ctx.tray.retry_failed_requested.emit()
    assert errors


def test_undo_command_sends_ctrl_z(ctx, monkeypatch):
    sent = []
    monkeypatch.setattr(
        app_mod, "paste_active_window", lambda ids, **k: sent.append(k["combo"]) or True
    )
    ctx.controller.undo_requested.emit()
    assert sent == ["ctrl+z"]


def test_history_uses_retention_setting(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod.paths, "history_path", lambda: tmp_path / "h.jsonl")
    h = app_mod._make_history(Settings(history_retention_days=7))
    assert h._retention_days == 7


def test_lowering_history_limit_to_zero_deletes_file(ctx, monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod, "save_settings", lambda s: None)
    monkeypatch.setattr(app_mod, "set_autostart", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "list_input_devices", lambda: ())
    ctx.history.append(Session(raw_text="gizli", corrected_text="Gizli."))
    assert (tmp_path / "history.jsonl").exists()

    class FakeDialog:
        health_requested = _FakeSignal()

        def __init__(self, settings, devices, parent=None):
            self._settings = settings

        def exec(self):
            return 1

        def result_settings(self):
            return self._settings.model_copy(update={"history_limit": 0})

    monkeypatch.setattr(app_mod, "SettingsDialog", FakeDialog)
    app_mod._open_settings(ctx)
    assert not (tmp_path / "history.jsonl").exists()


def test_startup_prunes_expired_history_from_disk(qtbot, tmp_path, monkeypatch):
    """Saklama süresi dolmuş dikteler yalnızca listeden gizlenmemeli, açılışta diskten de
    silinmeli (kullanıcı hiç kayıt yapmasa bile)."""
    from datetime import datetime, timedelta

    from dikte.core.history import History

    path = tmp_path / "history.jsonl"
    History(path, 200).append(
        Session(
            raw_text="eski",
            corrected_text="Eski gizli.",
            created_at=datetime.now() - timedelta(days=30),
        )
    )
    History(path, 200).append(Session(raw_text="yeni", corrected_text="Yeni."))
    monkeypatch.setattr(app_mod.paths, "history_path", lambda: path)
    monkeypatch.setattr(app_mod.paths, "failed_audio_path", lambda: tmp_path / "failed.wav")
    c = app_mod.build_app(Settings(history_retention_days=7))
    for w in (c.window, c.overlay):
        qtbot.addWidget(w)
    content = path.read_text(encoding="utf-8")
    assert "Eski gizli." not in content and "Yeni." in content


def test_quit_resumes_media_after_queued_pause(ctx, qtbot):
    """Kayıt başlar başlamaz çıkılırsa kuyruktaki pause(), resume()'dan sonra çalışıp
    medyayı duraklatılmış bırakmamalı."""
    import threading

    gate = threading.Event()
    calls = []

    class SlowMedia:
        def pause(self):
            gate.wait(2)  # pause hâlâ medya havuzunda sürüyor
            calls.append("pause")

        def resume(self):
            calls.append("resume")

    ctx.settings = ctx.settings.model_copy(update={"pause_media": True})
    ctx.media = SlowMedia()
    ctx.controller.state_changed.emit(DictationState.RECORDING)
    threading.Timer(0.2, gate.set).start()
    app_mod._shutdown(ctx)
    qtbot.waitUntil(lambda: len(calls) == 2, timeout=3000)
    assert calls == ["pause", "resume"]


def test_qt_translator_translates_standard_buttons(qapp):
    from PySide6.QtCore import QCoreApplication

    translator = app_mod._install_qt_translator(qapp)
    try:
        assert translator is not None
        assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "İptal"
    finally:
        if translator is not None:
            qapp.removeTranslator(translator)


def test_qt_translator_falls_back_to_bundled_dir(qapp, tmp_path):
    import shutil

    from PySide6.QtCore import QLibraryInfo

    source = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    bundled = tmp_path / "translations"
    bundled.mkdir()
    shutil.copy(f"{source}/{app_mod.QT_TRANSLATION}.qm", bundled)
    translator = app_mod._install_qt_translator(
        qapp, search_dirs=(str(tmp_path / "yok"), str(bundled))
    )
    try:
        assert translator is not None
    finally:
        if translator is not None:
            qapp.removeTranslator(translator)


def test_missing_qt_translation_logs_warning(qapp, tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="dikte.app"):
        assert app_mod._install_qt_translator(qapp, search_dirs=(str(tmp_path),)) is None
    assert "çeviri" in caplog.text


def test_settings_health_request_opens_app_owned_health_dialog(ctx, monkeypatch):
    """Ayarlar → Hakkında → "Durum kontrolü…" uygulamanın kendi durum penceresini açar:
    model_downloaded bağlıdır ve pencere ayarlar diyaloğu silinince yok olmaz."""
    from PySide6.QtCore import QObject, Signal

    monkeypatch.setattr(app_mod, "list_input_devices", lambda: ())
    opened = []
    monkeypatch.setattr(app_mod, "_show_health_dialog", lambda c, *a, **k: opened.append(k))

    class FakeDialog(QObject):
        health_requested = Signal()

        def __init__(self, settings, devices, parent=None):
            super().__init__()

        def exec(self):
            self.health_requested.emit()
            return 0

    monkeypatch.setattr(app_mod, "SettingsDialog", FakeDialog)
    app_mod._open_settings(ctx)
    assert opened == [{"modal": True}]


def test_modal_health_dialog_is_parented_to_main_window_and_reloads_model(ctx, monkeypatch):
    warmed = []
    monkeypatch.setattr(ctx.controller, "warm_up", lambda: warmed.append(True))
    app_mod._show_health_dialog(ctx, (), modal=True)
    dialog = ctx.health_dialog
    assert dialog is not None
    assert dialog.parent() is ctx.window and dialog.isModal()
    dialog.model_downloaded.emit()
    assert warmed == [True]
    dialog.close()
