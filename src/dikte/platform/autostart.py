from __future__ import annotations

import logging
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


# Desktop Entry belirtimi, "Exec anahtarı": bu karakterleri içeren argüman çift tırnağa
# alınmalı; tırnak içinde `"`, `` ` ``, `$` ve `\` ters bölüyle kaçırılır. `%` alan kodu
# başlattığından her yerde `%%` olarak yazılır. shlex.quote'un tek tırnağı belirtimde yok.
_DESKTOP_RESERVED = set(" \t\n\"'\\><~|&;$*?#()`")
_DESKTOP_QUOTED_ESCAPES = {'"': '\\"', "`": "\\`", "$": "\\$", "\\": "\\\\"}


class AutostartError(RuntimeError):
    """Otomatik başlatma kaydı yazılamadı/silinemedi; mesaj kullanıcıya gösterilebilir."""


def desktop_exec_arg(arg: str) -> str:
    """Bir argümanı .desktop `Exec=` satırına belirtime uygun biçimde yazar (argüman
    düzeyi; dosyaya yazarken ayrıca dize kaçışı uygulanır, bkz. `_desktop_string`)."""
    if any(ch in _DESKTOP_RESERVED for ch in arg):
        inner = "".join(_DESKTOP_QUOTED_ESCAPES.get(ch, ch) for ch in arg)
        arg = f'"{inner}"'
    return arg.replace("%", "%%")


def _desktop_string(value: str) -> str:
    """Desktop Entry `string` türü kaçışı: tırnak kuralından önce uygulanır, yani tırnak
    içindeki gerçek bir ters bölü dosyada dört ters bölü olarak görünür."""
    return (
        value.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    )


def _desktop_entry_enabled(body: str) -> bool:
    """`Hidden=true` ya da `X-GNOME-Autostart-enabled=false` girdiyi devre dışı bırakır."""
    in_main = False
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_main = line == "[Desktop Entry]"
            continue
        if not in_main or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().lower()
        if key == "Hidden" and value == "true":
            return False
        if key == "X-GNOME-Autostart-enabled" and value == "false":
            return False
    return True


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
        body = DESKTOP_TEMPLATE.format(name=APP_NAME, command=_desktop_string(value))
        self._path.write_text(body, encoding="utf-8")

    def get_value(self, key, name):
        """Girdi yoksa ya da `Hidden=true` vb. ile devre dışıysa None."""
        try:
            body = self._path.read_text(encoding="utf-8")
        except OSError:
            return None
        return body if _desktop_entry_enabled(body) else None

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
    """Otomatik başlatmada çalıştırılacak komut satırı (posix: .desktop `Exec=` biçimi)."""
    if posix is None:
        posix = sys.platform != "win32"
    if posix:
        exe = exe_path or (sys.executable if getattr(sys, "frozen", False) else None)
        if exe is not None:
            return f"{desktop_exec_arg(exe)} --minimized"
        return f"{desktop_exec_arg(sys.executable)} -m dikte --minimized"
    if exe_path is not None:
        return f'"{exe_path}" --minimized'
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
    return f'"{pythonw}" -m dikte --minimized'


def set_autostart(enabled: bool, exe_path: str | None = None, reg=None) -> None:
    """Otomatik başlatmayı açar/kapatır; başarısızlıkta `AutostartError` yükseltir.

    Çağıran, hatayı kullanıcıya göstermeli ama diğer ayarların kaydını engellememelidir."""
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
    except OSError as exc:
        log.exception("otomatik başlatma ayarlanamadı")
        if getattr(r, "posix", False):
            hint = (
                "~/.config/autostart klasörünün yazılabilir olduğunu denetleyip "
                "ayarı yeniden kaydedin."
            )
        else:
            hint = (
                "Ayarı yeniden kaydetmeyi deneyin; sorun sürerse Windows Ayarlar → "
                "Uygulamalar → Başlangıç bölümünden Dikte'yi elle açın."
            )
        action = "açılamadı" if enabled else "kapatılamadı"
        raise AutostartError(f"Otomatik başlatma {action} ({exc}). {hint}") from exc


def is_autostart_enabled(reg=None) -> bool:
    r = _reg(reg)
    return bool(r and r.get_value(RUN_KEY, VALUE_NAME))
