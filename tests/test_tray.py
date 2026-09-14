from dikte.core.state import DictationState
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
