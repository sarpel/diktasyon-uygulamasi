from dikte.core.state import DictationState, Session
from dikte.ui.tray import TrayIcon


def make(qtbot):
    t = TrayIcon("Ctrl+Alt+Space")
    qtbot.addWidget(t.contextMenu())
    return t


def test_initial_tooltip_says_loading(qtbot):
    t = make(qtbot)
    assert "Model yükleniyor" in t.toolTip() and "Ctrl+Alt+Space" in t.toolTip()


def test_ready_switches_tooltip(qtbot):
    t = make(qtbot)
    t.set_ready(True)
    assert "Hazır" in t.toolTip()


def test_recording_state_renames_toggle_action(qtbot):
    t = make(qtbot)
    t.set_state(DictationState.RECORDING)
    assert t._toggle_action.text() == "Kaydı Durdur"
    assert "Kaydediliyor" in t.toolTip()


def test_toggle_action_disabled_while_busy(qtbot):
    t = make(qtbot)
    t.set_state(DictationState.TRANSCRIBING)
    assert not t._toggle_action.isEnabled()
    t.set_state(DictationState.RESULT)
    assert t._toggle_action.isEnabled() and t._toggle_action.text() == "Kaydı Başlat"


def test_menu_actions_emit_signals(qtbot):
    t = make(qtbot)
    actions = {a.text(): a for a in t.contextMenu().actions() if a.text()}
    with qtbot.waitSignal(t.show_requested):
        actions["Pencereyi Göster"].trigger()
    with qtbot.waitSignal(t.settings_requested):
        actions["Ayarlar…"].trigger()
    with qtbot.waitSignal(t.quit_requested):
        actions["Çıkış"].trigger()
    with qtbot.waitSignal(t.toggle_requested):
        actions["Kaydı Başlat"].trigger()


def test_set_hotkey_label_updates_tooltip(qtbot):
    t = make(qtbot)
    t.set_hotkey_label("Ctrl+Shift+D")
    assert "Ctrl+Shift+D" in t.toolTip()


def test_cancel_action_enabled_only_while_busy(qtbot):
    t = make(qtbot)
    assert not t._cancel_action.isEnabled()
    t.set_state(DictationState.RECORDING)
    assert t._cancel_action.isEnabled()
    t.set_state(DictationState.CORRECTING)
    assert t._cancel_action.isEnabled()
    t.set_state(DictationState.RESULT)
    assert not t._cancel_action.isEnabled()


def test_cancel_action_emits_signal(qtbot):
    t = make(qtbot)
    t.set_state(DictationState.RECORDING)
    with qtbot.waitSignal(t.cancel_requested):
        t._cancel_action.trigger()


def test_set_recent_populates_submenu_with_given_count(qtbot):
    t = make(qtbot)
    t.set_recent((Session(corrected_text="Eski."), Session(corrected_text="Yeni.")))
    assert len(t._recent_menu.actions()) == 2
    assert t._recent_menu.isEnabled() and t._copy_recent_action.isEnabled()


def test_set_recent_submenu_item_emits_copy_requested_with_full_text(qtbot):
    t = make(qtbot)
    t.set_recent((Session(corrected_text="Uzun bir dikte metni burada."),))
    with qtbot.waitSignal(t.copy_requested) as blocker:
        t._recent_menu.actions()[0].trigger()
    assert blocker.args == ["Uzun bir dikte metni burada."]


def test_copy_recent_action_copies_most_recent_session(qtbot):
    t = make(qtbot)
    t.set_recent((Session(corrected_text="Eski."), Session(corrected_text="Yeni.")))
    with qtbot.waitSignal(t.copy_requested) as blocker:
        t._copy_recent_action.trigger()
    assert blocker.args == ["Yeni."]


def test_set_recent_limits_to_five_and_previews_forty_chars(qtbot):
    t = make(qtbot)
    sessions = tuple(Session(corrected_text=f"Kayıt {i} " * 10) for i in range(8))
    t.set_recent(sessions)
    assert len(t._recent_menu.actions()) == 5
    assert all(len(a.text()) <= 40 for a in t._recent_menu.actions())


def test_recent_disabled_when_no_history(qtbot):
    t = make(qtbot)
    t.set_recent(())
    assert not t._copy_recent_action.isEnabled() and not t._recent_menu.isEnabled()


def _action(t, text):
    return next(a for a in t.contextMenu().actions() if a.text() == text)


def test_paste_last_action_emits_signal(qtbot):
    t = make(qtbot)
    with qtbot.waitSignal(t.paste_last_requested):
        _action(t, "Son sonucu yapıştır").trigger()


def test_retry_action_disabled_until_retry_available(qtbot):
    t = make(qtbot)
    action = _action(t, "Başarısız kaydı yeniden dene")
    assert not action.isEnabled()
    t.set_retry_available(True)
    assert action.isEnabled()
    with qtbot.waitSignal(t.retry_failed_requested):
        action.trigger()
    t.set_retry_available(False)
    assert not action.isEnabled()
