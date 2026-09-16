from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)


def _win32_probe() -> str:
    import ctypes
    from ctypes import wintypes

    hwnd = ctypes.windll.user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(len(buf))
        ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        if not ok:
            return ""
        return Path(buf.value).stem
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _linux_probe() -> str:
    win_id = subprocess.check_output(["xdotool", "getactivewindow"], timeout=2, text=True).strip()
    pid = subprocess.check_output(["xdotool", "getwindowpid", win_id], timeout=2, text=True).strip()
    return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()


def _default_probe() -> str:
    if sys.platform == "win32":
        return _win32_probe()
    if sys.platform.startswith("linux"):
        return _linux_probe()
    return ""


def foreground_process_name(probe: Callable[[], str] | None = None) -> str:
    """Ön plandaki pencerenin sürecinin alt adını (küçük harf) döndürür; hata olursa boş dize."""
    run = probe or _default_probe
    try:
        name = run()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        log.info("ön plan süreci alınamadı: %s", exc)
        return ""
    return name.strip().lower()
