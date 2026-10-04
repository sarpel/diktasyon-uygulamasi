"""Ön plandaki pencerenin süreç adını bulur (uygulama profili eşleştirmesi için).

Windows'ta user32/kernel32 ile, Linux'ta (yalnızca X11) `xdotool` + `/proc` ile okunur.
Wayland oturumunda ön plan uygulaması bilinemez (sonuç "bilinmiyor"dur).
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from dikte.platform.paste import is_wayland_session

log = logging.getLogger(__name__)


def _win32_probe() -> str:
    import ctypes
    from ctypes import wintypes

    hwnd = ctypes.windll.user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    query_limited_information = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
    handle = ctypes.windll.kernel32.OpenProcess(query_limited_information, False, pid.value)
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


_PROC_ROOT = Path("/proc")
_COMM_MAX_LEN = 15  # TASK_COMM_LEN (16) - NUL


def _run_xdotool(args: list[str]) -> str:
    return subprocess.check_output(args, timeout=2, text=True)


def _full_name_candidates(proc: Path) -> list[str]:
    names: list[str] = []
    with contextlib.suppress(OSError):
        names.append((proc / "exe").readlink().name)
    try:
        argv0 = (proc / "cmdline").read_bytes().split(b"\0", 1)[0]
    except OSError:
        argv0 = b""
    if argv0:
        names.append(Path(argv0.decode("utf-8", errors="replace")).name)
    return names


def linux_process_name(pid: str, *, proc_root: Path = _PROC_ROOT) -> str:
    """Sürecin adını döndürür. `/proc/<pid>/comm` 15 karakterde kesilir
    ("gnome-terminal-server" → "gnome-terminal-"); kesilmişse `exe` bağlantısının veya
    `cmdline` argv[0]'ın bu önekle başlayan taban adı kullanılır. Kısa `comm` olduğu gibi
    döner: yorumlanan uygulamalarda (ör. "terminator") `exe` yalnızca "python3" olurdu."""
    proc = proc_root / pid
    comm = (proc / "comm").read_text(encoding="utf-8").strip()
    if len(comm) < _COMM_MAX_LEN:
        return comm
    for name in _full_name_candidates(proc):
        if name.startswith(comm):
            return name
    return comm


def _linux_probe(
    run: Callable[[list[str]], str] = _run_xdotool, proc_root: Path = _PROC_ROOT
) -> str:
    win_id = run(["xdotool", "getactivewindow"]).strip()
    pid = run(["xdotool", "getwindowpid", win_id]).strip()
    return linux_process_name(pid, proc_root=proc_root)


def _default_probe() -> str:
    if sys.platform == "win32":
        return _win32_probe()
    if sys.platform.startswith("linux"):
        # Modül öznitelikleri çağrı anında çözülür (testler bunları değiştirebilsin).
        return _linux_probe(_run_xdotool, _PROC_ROOT)
    return ""


FOREGROUND_UNKNOWN_MESSAGE = (
    "Wayland oturumunda etkin uygulama algılanamıyor; uygulama profilleri uygulanmıyor, "
    "varsayılan ayarlar kullanılıyor."
)
_warned = {"wayland": False}


def probe_foreground_process(
    probe: Callable[[], str] | None = None, *, env: Mapping[str, str] | None = None
) -> str | None:
    """Ön plandaki pencerenin süreç adını küçük harfle döndürür; bilinmiyorsa None.

    None, "profil eşleşmedi" değil "hangi uygulama olduğu bilinmiyor" demektir: araç yok,
    izin yok, desteklenmeyen platform ya da Wayland oturumu. Wayland'de xdotool yalnızca
    XWayland pencerelerini görür; "etkin pencere" diye döndürdüğü yanlış olabileceğinden
    hiç sorulmaz (çağıran `FOREGROUND_UNKNOWN_MESSAGE` ile kullanıcıyı bir kez uyarabilir).
    Hata yükseltilmez."""
    if probe is None:
        if sys.platform.startswith("linux") and is_wayland_session(env):
            if not _warned["wayland"]:
                log.info("Wayland oturumu: ön plan uygulaması algılanamıyor, profiller atlanıyor")
                _warned["wayland"] = True
            return None
        probe = _default_probe
    try:
        name = probe()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        log.info("ön plan süreci alınamadı: %s", exc)
        return None
    return name.strip().lower() or None


def foreground_process_name(
    probe: Callable[[], str] | None = None, *, env: Mapping[str, str] | None = None
) -> str:
    """Ön plandaki pencerenin süreç adını küçük harfle döndürür (Windows'ta ".exe"siz).

    Ad alınamazsa (araç yok, izin yok, desteklenmeyen platform, Wayland) boş dize döner;
    hata yükseltilmez. "Bilinmiyor"u ayırt etmek için `probe_foreground_process` kullanın."""
    return probe_foreground_process(probe, env=env) or ""
