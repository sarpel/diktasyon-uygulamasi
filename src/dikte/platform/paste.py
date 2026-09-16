"""Panodaki metni ön plandaki uygulamaya yapıştırır ya da doğrudan yazar.

Windows'ta eski `keybd_event` yerine `SendInput` kullanılır (Unicode giriş de dahil).
Linux'ta X11 için `xdotool`, Wayland için `wtype` gerekir; ikisi de yoksa yapıştırma/yazma
sessizce atlanır ve metin panoda kalır. Varsayılan tuş bileşimi Ctrl+V'dir; Ctrl+Shift+V
(bazı terminallerde/uygulamalarda "yapıştır" için ayrı kısayoldur) de desteklenir.
"""

from __future__ import annotations

import ctypes
import logging
import shutil
import subprocess
import sys
from collections.abc import Callable
from typing import Literal

log = logging.getLogger(__name__)

VK_CONTROL, VK_SHIFT, VK_V, KEYEVENTF_KEYUP = 0x11, 0x10, 0x56, 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
_PASTE_TIMEOUT_S = 3
_warned = {"tools": False}

KeyCombo = Literal["ctrl+v", "ctrl+shift+v"]

_COMBO_VKS: dict[KeyCombo, tuple[int, ...]] = {
    "ctrl+v": (VK_CONTROL, VK_V),
    "ctrl+shift+v": (VK_CONTROL, VK_SHIFT, VK_V),
}
_WTYPE_ARGS: dict[KeyCombo, list[str]] = {
    "ctrl+v": ["-M", "ctrl", "v", "-m", "ctrl"],
    "ctrl+shift+v": ["-M", "ctrl", "-M", "shift", "v", "-m", "shift", "-m", "ctrl"],
}


# Yalnızca ctypes ilkel türleriyle kurulu; tanım Linux'ta da güvenle yapılabilir
# (Windows API'sine erişim yalnızca _send_windows/_type_windows içinde, win32'de olur).
class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ki", _KEYBDINPUT)]


def foreground_window_id() -> int | None:
    """Ön plandaki pencerenin tanıtıcısı; yalnızca Windows'ta bilinir."""
    if sys.platform == "win32":
        return int(ctypes.windll.user32.GetForegroundWindow())
    return None


def build_key_inputs(vks: tuple[int, ...]) -> list[tuple[int, int]]:
    """Verilen sanal tuşlar için önce sırayla bas, sonra ters sırayla bırak listesi üretir."""
    return [(vk, 0) for vk in vks] + [(vk, KEYEVENTF_KEYUP) for vk in reversed(vks)]


def _send_windows(combo: KeyCombo = "ctrl+v") -> bool:
    user32 = ctypes.windll.user32
    events = build_key_inputs(_COMBO_VKS[combo])
    arr = (_INPUT * len(events))(
        *(
            _INPUT(type=INPUT_KEYBOARD, ki=_KEYBDINPUT(vk, 0, flags, 0, None))
            for vk, flags in events
        )
    )
    sent = user32.SendInput(len(arr), arr, ctypes.sizeof(_INPUT))
    return sent == len(arr)


def _type_windows(text: str) -> bool:
    events: list[tuple[int, int]] = []
    for ch in text:
        scan = ord(ch)
        events.append((scan, KEYEVENTF_UNICODE))
        events.append((scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    user32 = ctypes.windll.user32
    arr = (_INPUT * len(events))(
        *(
            _INPUT(type=INPUT_KEYBOARD, ki=_KEYBDINPUT(0, scan, flags, 0, None))
            for scan, flags in events
        )
    )
    sent = user32.SendInput(len(arr), arr, ctypes.sizeof(_INPUT))
    return sent == len(arr)


def _send_linux(combo: KeyCombo = "ctrl+v") -> bool:
    """Önce xdotool (X11), başarısız olursa wtype (Wayland) denenir."""
    found_tool = False
    for name, args in (
        ("xdotool", ["key", "--clearmodifiers", combo]),
        ("wtype", _WTYPE_ARGS[combo]),
    ):
        path = shutil.which(name)
        if not path:
            continue
        found_tool = True
        result = subprocess.run([path, *args], check=False, timeout=_PASTE_TIMEOUT_S)
        if result.returncode == 0:
            return True
        log.warning("%s yapıştırma komutu başarısız (çıkış kodu %s)", name, result.returncode)
    if not found_tool and not _warned["tools"]:
        log.warning(
            "otomatik yapıştırma için xdotool (X11) veya wtype (Wayland) gerekli; "
            "metin panoda kaldı"
        )
        _warned["tools"] = True
    return False


def _type_linux(text: str) -> bool:
    """Önce xdotool (X11), başarısız olursa wtype (Wayland) ile metni doğrudan yazar."""
    found_tool = False
    for name, args in (
        ("xdotool", ["type", "--clearmodifiers", "--", text]),
        ("wtype", ["--", text]),
    ):
        path = shutil.which(name)
        if not path:
            continue
        found_tool = True
        result = subprocess.run([path, *args], check=False, timeout=_PASTE_TIMEOUT_S)
        if result.returncode == 0:
            return True
        log.warning("%s yazma komutu başarısız (çıkış kodu %s)", name, result.returncode)
    if not found_tool:
        log.warning(
            "otomatik yazma için xdotool (X11) veya wtype (Wayland) gerekli; metin panoda kaldı"
        )
    return False


def send_paste_keystroke(
    sender: Callable[[], object] | None = None, *, combo: KeyCombo = "ctrl+v"
) -> bool:
    """`combo` tuş bileşimini gönderir. `sender` testler için enjekte edilebilir."""
    if sender is not None:
        sender()
        return True
    try:
        return _send_windows(combo) if sys.platform == "win32" else _send_linux(combo)
    except (OSError, subprocess.SubprocessError) as exc:
        log.error("yapıştırma tuşu gönderilemedi: %s", exc)
        return False


def type_unicode_text(text: str, sender: Callable[[str], bool] | None = None) -> bool:
    """Metni panoyu kullanmadan doğrudan Unicode karakter karakter yazar (yapıştırma yedeği)."""
    if sender is not None:
        return bool(sender(text))
    try:
        return _type_windows(text) if sys.platform == "win32" else _type_linux(text)
    except (OSError, subprocess.SubprocessError) as exc:
        log.error("metin yazılamadı: %s", exc)
        return False


def paste_active_window(
    own_win_ids: set[int],
    sender: Callable[[], object] | None = None,
    *,
    combo: KeyCombo = "ctrl+v",
) -> bool:
    """Ön plandaki pencere Dikte'nin kendisi değilse yapıştırır; yapıştırdıysa True döner."""
    foreground = foreground_window_id()
    if foreground is not None and foreground in own_win_ids:
        return False
    return send_paste_keystroke(sender, combo=combo)
