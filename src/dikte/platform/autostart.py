from __future__ import annotations

import logging
import shlex
import sys
from pathlib import Path

from dikte import APP_NAME

log = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Dikte"

DESKTOP_TEMPLATE = """[Desktop Entry]
Type=Application
Version=1.0
Name={name}
Comment=Türkçe sesli dikte
Exec={command}
Icon=dikte
Terminal=false
X-GNOME-Autostart-enabled=true
"""


class _WinReg:
    """HKCU\\...\\Run anahtarına yazan Windows arka ucu."""

    posix = False

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


class _XdgAutostart:
    """~/.config/autostart/dikte.desktop dosyasını yöneten XDG arka ucu.

    _WinReg ile aynı key/name/value arayüzünü sunar; key ve name yok sayılır.
    """

    posix = True

    def __init__(self, path: Path | None = None):
        self._path = path or (Path.home() / ".config" / "autostart" / "dikte.desktop")

    @property
    def path(self) -> Path:
        return self._path

    def set_value(self, key, name, value):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = DESKTOP_TEMPLATE.format(name=APP_NAME, command=value)
        self._path.write_text(body, encoding="utf-8")

    def get_value(self, key, name):
        try:
            return self._path.read_text(encoding="utf-8")
        except OSError:
            return None

    def delete_value(self, key, name):
        self._path.unlink(missing_ok=True)


def _reg(reg):
    if reg is not None:
        return reg
    if sys.platform == "win32":
        return _WinReg()
    if sys.platform.startswith(("linux", "freebsd")):
        return _XdgAutostart()
    log.info("otomatik başlatma bu platformda desteklenmiyor: %s", sys.platform)
    return None


def launch_command(exe_path: str | None = None, posix: bool | None = None) -> str:
    """Otomatik başlatmada çalıştırılacak komut satırı."""
    if posix is None:
        posix = sys.platform != "win32"
    if posix:
        exe = exe_path or (sys.executable if getattr(sys, "frozen", False) else None)
        if exe is not None:
            return f"{shlex.quote(exe)} --minimized"
        return f"{shlex.quote(sys.executable)} -m dikte --minimized"
    if exe_path is not None:
        return f'"{exe_path}" --minimized'
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
    return f'"{pythonw}" -m dikte --minimized'


def set_autostart(enabled: bool, exe_path: str | None = None, reg=None) -> None:
    r = _reg(reg)
    if r is None:
        return
    try:
        if enabled:
            r.set_value(
                RUN_KEY, VALUE_NAME, launch_command(exe_path, posix=getattr(r, "posix", False))
            )
        else:
            r.delete_value(RUN_KEY, VALUE_NAME)
    except OSError:
        # Otomatik başlatma en iyi çaba (best-effort) bir kolaylıktır; kayıt defteri/dosya
        # yazma izni sorunu tüm ayarların kaydedilmesini engellememeli.
        log.exception("otomatik başlatma ayarlanamadı")


def is_autostart_enabled(reg=None) -> bool:
    r = _reg(reg)
    return bool(r and r.get_value(RUN_KEY, VALUE_NAME))
