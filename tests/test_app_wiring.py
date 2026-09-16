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


def test_build_app_creates_mode_hotkeys(ctx):
    from dikte.platform.hotkey import GlobalHotkey

    assert isinstance(ctx.hotkey_translate, GlobalHotkey)
    assert isinstance(ctx.hotkey_prompt, GlobalHotkey)
    assert ctx.hotkey_translate._id != ctx.hotkey._id != ctx.hotkey_prompt._id


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


def test_paste_still_happens_when_raise_on_result_activates_window(ctx, qtbot, monkeypatch):
    """result_ready, RESULT durumuna geçiş penceresini aktive etmeden önce işlenmeli
    (aktivasyon artık ertelenmiş); aksi halde yapıştırma hedefi kaybolur."""
    ctx.window.raise_on_result = True
    pasted = []
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: pasted.append(ids) or True)
    ctx.controller.state_changed.emit(DictationState.RESULT)
    ctx.controller.result_ready.emit("Merhaba.")
    assert len(pasted) == 1


def test_restore_clipboard_after_paste(ctx, monkeypatch, qtbot):
    from PySide6.QtWidgets import QApplication

    ctx.settings = ctx.settings.model_copy(update={"restore_clipboard": True})
    QApplication.clipboard().setText("eski")
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: True)
    app_mod._on_result_ready(ctx, "yeni")
    assert QApplication.clipboard().text() == "yeni"
    qtbot.waitUntil(lambda: QApplication.clipboard().text() == "eski", timeout=2000)


def test_clipboard_not_restored_when_paste_skipped(ctx, monkeypatch, qtbot):
    from PySide6.QtWidgets import QApplication

    ctx.settings = ctx.settings.model_copy(update={"restore_clipboard": True})
    QApplication.clipboard().setText("eski")
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: False)
    app_mod._on_result_ready(ctx, "yeni")
    qtbot.wait(400)
    assert QApplication.clipboard().text() == "yeni"


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
    ctx.window.text_edited.emit("A düzenlendi.")
    assert ctx.controller.session.corrected_text == "A düzenlendi."


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
    monkeypatch.setattr(app_mod, "_on_result_ready", lambda c, t: delivered.append(t))
    ctx.window.repaste_requested.emit("yeniden yapıştırılan metin")
    assert not ctx.window.isVisible()
    qtbot.waitUntil(lambda: delivered == ["yeniden yapıştırılan metin"], timeout=1000)


def test_status_info_set_when_ready(ctx):
    ctx.stt._compute_type = "float16"
    ctx.controller.ready_changed.emit(True)
    assert "float16" in ctx.window.status_info.text()


def test_low_vram_shows_status_bar_warning(ctx, monkeypatch):
    from dikte.platform.gpu_info import VramInfo

    monkeypatch.setattr(app_mod, "query_vram", lambda: VramInfo(7500, 8192))
    app_mod._refresh_status_info(ctx)
    msg = ctx.window.statusBar().currentMessage()
    assert "Boş VRAM düşük" in msg


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


def test_stt_model_load_error_shows_health_dialog(ctx, monkeypatch):
    from dikte.core.health import HealthItem

    fake_items = (
        HealthItem("GPU", True, "1 CUDA aygıtı", ""),
        HealthItem("Whisper modeli", False, "indirilmemiş", "indirin"),
        HealthItem("LLM", True, "kapalı", ""),
    )
    monkeypatch.setattr(app_mod, "check_health", lambda *a, **k: fake_items)
    assert ctx.health_dialog is None
    ctx.controller.error.emit("STT modeli yüklenemedi: dosya bulunamadı")
    assert ctx.health_dialog is not None
    assert len(ctx.health_dialog._labels) == 3


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
