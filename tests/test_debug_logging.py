import logging

from dikte.config import Settings
from dikte.logging_setup import set_debug
from dikte.ui.settings_dialog import SettingsDialog


def test_debug_logging_defaults_off():
    assert Settings().debug_logging is False


def test_set_debug_switches_root_level_and_quiet_libraries():
    root = logging.getLogger()
    old = root.level
    try:
        set_debug(True)
        assert root.level == logging.DEBUG
        assert logging.getLogger("httpcore").level == logging.INFO  # bayt bayt döküm olmasın
        set_debug(False)
        assert root.level == logging.INFO
    finally:
        root.setLevel(old)


def test_debug_checkbox_round_trips(qtbot):
    d = SettingsDialog(Settings(), ())
    qtbot.addWidget(d)
    assert not d.debug_check.isChecked()
    d.debug_check.setChecked(True)
    assert d.result_settings().debug_logging is True


def test_qt_warnings_reach_the_log(qtbot, caplog):
    from PySide6.QtCore import qInstallMessageHandler, qWarning

    from dikte.logging_setup import _log_qt_message

    previous = qInstallMessageHandler(_log_qt_message)
    try:
        with caplog.at_level(logging.DEBUG, logger="qt"):
            qWarning("deneme-uyarısı")
    finally:
        qInstallMessageHandler(previous)
    assert any("deneme-uyarısı" in r.getMessage() for r in caplog.records)
