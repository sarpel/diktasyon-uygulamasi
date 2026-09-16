"""Panodaki metni ön plandaki uygulamaya Ctrl+V ile yapıştırır.

Windows'ta `keybd_event` kullanılır. Linux'ta X11 için `xdotool`, Wayland için `wtype`
gerekir; ikisi de yoksa yapıştırma sessizce atlanır ve metin panoda kalır.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from collections.abc import Callable

log = logging.getLogger(__name__)

VK_CONTROL, VK_V, KEYEVENTF_KEYUP = 0x11, 0x56, 0x0002
_PASTE_TIMEOUT_S = 3
_warned = {"tools": False}


def foreground_window_id() -> int | None:
    """Ön plandaki pencerenin tanıtıcısı; yalnızca Windows'ta bilinir."""
    if sys.platform == "win32":
        import ctypes

        return int(ctypes.windll.user32.GetForegroundWindow())
    return None


def _send_windows() -> bool:
    import ctypes

    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    return True


def _send_linux() -> bool:
    xdotool = shutil.which("xdotool")
    if xdotool:
        subprocess.run(
            [xdotool, "key", "--clearmodifiers", "ctrl+v"],
            check=False,
            timeout=_PASTE_TIMEOUT_S,
        )
        return True
    wtype = shutil.which("wtype")
    if wtype:
        subprocess.run(
            [wtype, "-M", "ctrl", "v", "-m", "ctrl"], check=False, timeout=_PASTE_TIMEOUT_S
        )
        return True
    if not _warned["tools"]:
        log.warning(
            "otomatik yapıştırma için xdotool (X11) veya wtype (Wayland) gerekli; metin panoda kaldı"
        )
        _warned["tools"] = True
    return False


def send_paste_keystroke(sender: Callable[[], object] | None = None) -> bool:
    """Ctrl+V tuş bileşimini gönderir. `sender` testler için enjekte edilebilir."""
    if sender is not None:
        sender()
        return True
    try:
        return _send_windows() if sys.platform == "win32" else _send_linux()
    except (OSError, subprocess.SubprocessError) as exc:
        log.error("yapıştırma tuşu gönderilemedi: %s", exc)
        return False


def paste_active_window(own_win_ids: set[int], sender: Callable[[], object] | None = None) -> bool:
    """Ön plandaki pencere Dikte'nin kendisi değilse yapıştırır; yapıştırdıysa True döner."""
    foreground = foreground_window_id()
    if foreground is not None and foreground in own_win_ids:
        return False
    return send_paste_keystroke(sender)
