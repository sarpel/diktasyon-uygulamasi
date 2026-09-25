"""Ayarlar → Ses: mikrofonun adla saklanması, Windows'ta WASAPI süzmesi, eksik cihaz."""

from types import SimpleNamespace

from dikte.config import AudioSettings, Settings
from dikte.ui.settings.audio_tab import AudioTab, InputDevice, visible_devices

DEVICES = (
    InputDevice(1, "Mikrofon (Realtek)", "MME"),
    InputDevice(5, "Mikrofon (Realtek)", "Windows WASAPI"),
    InputDevice(6, "USB Mic", "Windows WASAPI"),
    InputDevice(9, "USB Mic", "Windows DirectSound"),
)


def _tab(qtbot, settings=None, devices=DEVICES, platform="linux"):
    tab = AudioTab(settings or Settings(), devices, platform=platform)
    qtbot.addWidget(tab)
    return tab


def _names(tab):
    return [tab.device_combo.itemText(i) for i in range(tab.device_combo.count())]


def test_windows_lists_only_wasapi_devices():
    shown = visible_devices(DEVICES, platform="win32")
    assert [(d.index, d.name) for d in shown] == [(5, "Mikrofon (Realtek)"), (6, "USB Mic")]


def test_windows_falls_back_to_all_when_no_wasapi():
    devices = (InputDevice(1, "A", "MME"), InputDevice(2, "B", "MME"))
    assert [d.name for d in visible_devices(devices, platform="win32")] == ["A", "B"]


def test_each_name_appears_once_off_windows():
    assert [d.name for d in visible_devices(DEVICES, platform="linux")] == [
        "Mikrofon (Realtek)",
        "USB Mic",
    ]


def test_accepts_legacy_index_name_tuples_and_objects():
    obj = SimpleNamespace(index=4, name="Obj Mic", hostapi="ALSA")
    shown = visible_devices(((0, "Tuple Mic"), obj), platform="linux")
    assert [(d.index, d.name) for d in shown] == [(0, "Tuple Mic"), (4, "Obj Mic")]


def test_system_default_is_first_entry(qtbot):
    tab = _tab(qtbot)
    assert _names(tab)[0] == "Sistem varsayılanı"
    assert tab.device_combo.currentData() is None


def test_device_saved_by_name_not_index(qtbot):
    tab = _tab(qtbot)
    tab.device_combo.setCurrentIndex(tab.device_combo.findData("USB Mic"))
    audio = tab.apply(Settings()).audio
    assert audio.device_name == "USB Mic" and audio.device_index is None


def test_saved_name_is_preselected(qtbot):
    tab = _tab(qtbot, Settings(audio=AudioSettings(device_name="USB Mic")))
    assert tab.device_combo.currentData() == "USB Mic"
    assert tab.device_warning_label.isHidden()


def test_missing_saved_device_is_marked_and_kept(qtbot):
    tab = _tab(qtbot, Settings(audio=AudioSettings(device_name="Kulaklık")))
    assert tab.device_combo.currentText() == "Kulaklık (bulunamadı)"
    assert not tab.device_warning_label.isHidden()
    assert "Kulaklık" in tab.device_warning_label.text()
    assert tab.apply(Settings()).audio.device_name == "Kulaklık"


def test_legacy_index_preselects_device_once(qtbot):
    tab = _tab(qtbot, Settings(audio=AudioSettings(device_index=6)))
    assert tab.device_combo.currentData() == "USB Mic"
    audio = tab.apply(Settings(audio=AudioSettings(device_index=6))).audio
    assert audio.device_name == "USB Mic" and audio.device_index is None


def test_legacy_index_not_found_falls_back_to_default(qtbot):
    tab = _tab(qtbot, Settings(audio=AudioSettings(device_index=42)))
    assert tab.device_combo.currentData() is None


def test_devices_are_listed_lazily_when_not_given(qtbot):
    calls = []

    def provider():
        calls.append(1)
        return (InputDevice(2, "Tembel Mic", "ALSA"),)

    tab = AudioTab(Settings(), None, device_provider=provider, platform="linux")
    qtbot.addWidget(tab)
    assert calls == [1] and "Tembel Mic" in _names(tab)


def test_mic_test_uses_selected_device(qtbot):
    seen = []

    class FakeAudioRecorder:
        def __init__(self, audio):
            seen.append(audio)

    tab = _tab(qtbot)
    tab.device_combo.setCurrentIndex(tab.device_combo.findData("USB Mic"))
    import dikte.ui.settings.audio_tab as audio_mod

    original = audio_mod.AudioRecorder
    audio_mod.AudioRecorder = FakeAudioRecorder
    try:
        tab._default_recorder()
    finally:
        audio_mod.AudioRecorder = original
    assert seen[0].device_name == "USB Mic" and seen[0].device_index == 6


def test_dialog_device_list_comes_from_recorder(monkeypatch):
    import dikte.audio.recorder as recorder_mod
    from dikte.ui.settings_dialog import list_input_devices

    fake = [SimpleNamespace(name="USB Mic", index=7, hostapi="Windows WASAPI")]
    monkeypatch.setattr(recorder_mod, "list_input_devices", lambda: fake)
    assert list_input_devices() == (InputDevice(7, "USB Mic", "Windows WASAPI"),)
