from PySide6.QtWidgets import QDialog

from dikte.config import Settings
from dikte.ui.settings_dialog import SettingsDialog

DEVICES = ((0, "Mikrofon A"), (3, "USB Mic"))


def test_dialog_populates_from_settings(qtbot):
    d = SettingsDialog(Settings(), DEVICES)
    qtbot.addWidget(d)
    assert d.hotkey_edit.text() == "ctrl+alt+space"
    assert d.provider_combo.currentText() == "ollama"
    assert d.device_combo.count() == 3  # "Sistem varsayılanı" + 2


def test_result_settings_returns_new_object_with_changes(qtbot):
    s = Settings()
    d = SettingsDialog(s, DEVICES)
    qtbot.addWidget(d)
    d.hotkey_edit.setText("ctrl+shift+d")
    d.device_combo.setCurrentIndex(2)
    d.autostart_check.setChecked(False)
    d.llm_model_edit.setText("gemma4:e4b-it-qat")
    out = d.result_settings()
    assert out is not s and s.hotkey == "ctrl+alt+space"
    assert out.hotkey == "ctrl+shift+d" and out.audio.device_index == 3
    assert out.autostart is False and out.llm.model == "gemma4:e4b-it-qat"


def test_invalid_hotkey_blocks_accept(qtbot):
    d = SettingsDialog(Settings(), DEVICES)
    qtbot.addWidget(d)
    d.hotkey_edit.setText("space")
    d.accept()
    assert d.result() != QDialog.DialogCode.Accepted and "değiştirici" in d.error_label.text()


def test_batch_controls_round_trip(qtbot):
    from dikte.config import Settings, SttSettings

    s = Settings(stt=SttSettings(batch_enabled=False, batch_threshold_s=45.0))
    d = SettingsDialog(s, (), None)
    qtbot.addWidget(d)
    assert d.batch_check.isChecked() is False
    assert d.batch_threshold_spin.value() == 45

    d.batch_check.setChecked(True)
    d.batch_threshold_spin.setValue(90)
    out = d.result_settings()
    assert out.stt.batch_enabled is True and out.stt.batch_threshold_s == 90.0


def test_autostart_label_is_platform_neutral(qtbot):
    from dikte.config import Settings

    d = SettingsDialog(Settings(), (), None)
    qtbot.addWidget(d)
    assert "Windows" not in d.autostart_check.text()


def test_llm_enable_and_keep_alive_round_trip(qtbot):
    from dikte.config import Settings

    d = SettingsDialog(Settings(), (), None)
    qtbot.addWidget(d)
    assert d.llm_enabled_check.isChecked() is True
    d.llm_enabled_check.setChecked(False)
    d.keep_alive_edit.setText("0")
    out = d.result_settings()
    assert out.llm.enabled is False and out.llm.keep_alive == "0"


def test_llm_fields_disabled_when_llm_off(qtbot):
    from dikte.config import Settings

    d = SettingsDialog(Settings(), (), None)
    qtbot.addWidget(d)
    d.llm_enabled_check.setChecked(False)
    assert not d.llm_model_edit.isEnabled() and not d.provider_combo.isEnabled()
