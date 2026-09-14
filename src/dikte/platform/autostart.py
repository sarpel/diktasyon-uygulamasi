from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Dikte"


class _WinReg:
    def __init__(self):
        import winreg

        self._w = winreg

    def set_value(self, key, name, value):
        with self._w.OpenKey(self._w.HKEY_CURRENT_USER, key, 0, self._w.KEY_SET_VALUE) as k:
            self._w.SetValueEx(k, name, 0, self._w.REG_SZ, value)

    def get_value(self, key, name):
        try:
            with self._w.OpenKey(self._w.HKEY_CURRENT_USER, key, 0, self._w.KEY_READ) as k:
                return self._w.QueryValueEx(k, name)[0]
        except FileNotFoundError:
            return None

    def delete_value(self, key, name):
        try:
            with self._w.OpenKey(self._w.HKEY_CURRENT_USER, key, 0, self._w.KEY_SET_VALUE) as k:
                self._w.DeleteValue(k, name)
        except FileNotFoundError:
            pass


def _reg(reg):
    if reg is not None:
        return reg
    if sys.platform != "win32":
        return None
    return _WinReg()


def launch_command(exe_path: str | None = None) -> str:
    if exe_path is not None:
        return f'"{exe_path}" --minimized'
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
    return f'"{pythonw}" -m dikte --minimized'


def set_autostart(enabled: bool, exe_path: str | None = None, reg=None) -> None:
    r = _reg(reg)
    if r is None:
        log.info("autostart yalnızca Windows'ta desteklenir")
        return
    if enabled:
        r.set_value(RUN_KEY, VALUE_NAME, launch_command(exe_path))
    else:
        r.delete_value(RUN_KEY, VALUE_NAME)


def is_autostart_enabled(reg=None) -> bool:
    r = _reg(reg)
    return bool(r and r.get_value(RUN_KEY, VALUE_NAME))
