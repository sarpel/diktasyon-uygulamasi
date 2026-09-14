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
