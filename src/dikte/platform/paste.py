"""Panodaki metni ön plandaki uygulamaya yapıştırır ya da doğrudan yazar.

Windows'ta eski `keybd_event` yerine `SendInput` kullanılır (Unicode giriş de dahil).
Linux'ta X11 için `xdotool`, Wayland için `wtype` gerekir; ikisi de yoksa yapıştırma/yazma
atlanır (bir uyarı günlüğe yazılır) ve metin panoda kalır. Tuş bileşimleri: Ctrl+V
(varsayılan), Ctrl+Shift+V (terminaller) ve "geri al" sesli komutu için Ctrl+Z.
"""

from __future__ import annotations

import ctypes
import logging
import shutil
import struct
import subprocess
import sys
from collections.abc import Callable
from typing import Literal

log = logging.getLogger(__name__)

VK_CONTROL, VK_SHIFT, VK_V, KEYEVENTF_KEYUP = 0x11, 0x10, 0x56, 0x0002
VK_Z = 0x5A  # "geri al" sesli komutu Ctrl+Z gönderir
VK_RETURN = 0x0D
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
_PASTE_TIMEOUT_S = 3
# xdotool'un varsayılan 12 ms/karakter gecikmesi ~250 karakterden uzun metinleri sabit
# zaman aşımında yarıda kestiriyordu; 1 ms ile yazılır, zaman aşımı uzunlukla ölçeklenir
# (xdotool Unicode karakterler için tuş haritası değiştirdiğinden karakter başına pay
# bırakılır).
_XDOTOOL_TYPE_DELAY_MS = "1"
_TYPE_TIMEOUT_PER_CHAR_S = 0.02
_warned = {"tools": False}

KeyCombo = Literal["ctrl+v", "ctrl+shift+v", "ctrl+z"]

_COMBO_VKS: dict[KeyCombo, tuple[int, ...]] = {
    "ctrl+v": (VK_CONTROL, VK_V),
    "ctrl+shift+v": (VK_CONTROL, VK_SHIFT, VK_V),
    "ctrl+z": (VK_CONTROL, VK_Z),
}
_WTYPE_ARGS: dict[KeyCombo, list[str]] = {
    "ctrl+v": ["-M", "ctrl", "v", "-m", "ctrl"],
    "ctrl+shift+v": ["-M", "ctrl", "-M", "shift", "v", "-m", "shift", "-m", "ctrl"],
    "ctrl+z": ["-M", "ctrl", "z", "-m", "ctrl"],
}


# Yalnızca ctypes ilkel türleriyle kurulu; tanım Linux'ta da güvenle yapılabilir
# (Windows API'sine erişim yalnızca _send_windows/_type_windows içinde, win32'de olur).
#
# Gerçek Win32 INPUT yapısı bir union (MOUSEINPUT/KEYBDINPUT/HARDWAREINPUT) içerir. SendInput,
# cbSize == sizeof(INPUT) olmasını şart koşar (Microsoft belgeleri: eşleşmezse çağrı tümüyle
# başarısız olur, kısmi işlem yapılmaz) — 64-bit'te bu 40 bayttır. Yalnızca {type, KEYBDINPUT}
# içeren eski tanım 32 bayttı; SendInput her zaman 0 döndürüyordu (hiçbir tuş vuruşu iletilmedi).
# DWORD/LONG Windows'ta her zaman 32 bittir (LLP64) — ama bu modül Linux'ta da import
# edilip test edilir, ve Linux'ta ctypes.c_long/c_ulong 64 bittir (LP64). Win32 ABI'siyle
# platformdan bağımsız eşleşmek için sabit genişlikli tipler kullanılır.
class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_int32),
        ("dy", ctypes.c_int32),
        ("mouseData", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_uint32),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_uint32), ("u", _INPUTUNION)]


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


def _utf16_code_units(text: str) -> list[int]:
    """`wScan` 16 bittir; BMP-dışı karakterler (emoji vb.) `ord(ch)` tek bir 16 bit alana
    sessizce (ctypes taşmasıyla) kırpılıyordu. Windows'un kendi KEYEVENTF_UNICODE sözleşmesi
    zaten UTF-16 kod birimleri ister — BMP-dışı karakterler için gerçek bir surrogate çifti
    (iki ayrı tuş vuruşu) gönderilir, tek bir kırpılmış değer değil."""
    raw = text.encode("utf-16-le")
    return list(struct.unpack(f"<{len(raw) // 2}H", raw))


def type_timeout_s(length: int) -> float:
    """Doğrudan yazma alt süreci için zaman aşımı: en az 3 sn, uzunlukla artar."""
    return _PASTE_TIMEOUT_S + length * _TYPE_TIMEOUT_PER_CHAR_S


_SHIFT_ENTER: tuple[tuple[int, int, int], ...] = (
    (VK_SHIFT, 0, 0),
    (VK_RETURN, 0, 0),
    (VK_RETURN, 0, KEYEVENTF_KEYUP),
    (VK_SHIFT, 0, KEYEVENTF_KEYUP),
)


def build_type_events(text: str) -> list[tuple[int, int, int]]:
    """Windows "yaz" modu için (wVk, wScan, dwFlags) listesi.

    Satır sonu Unicode tuş vuruşu olarak gönderilince bazı uygulamalar onu düşürüyor,
    sohbet uygulamaları ise Enter sayıp mesajı gönderiyordu; bu yüzden `\n` (ve `\r\n`,
    `\r`) sanal Shift+Enter olarak gönderilir — çoğu uygulamada "yeni satır" demektir."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    events: list[tuple[int, int, int]] = []
    for i, line in enumerate(normalized.split("\n")):
        if i:
            events.extend(_SHIFT_ENTER)
        for scan in _utf16_code_units(line) if line else ():
            events.append((0, scan, KEYEVENTF_UNICODE))
            events.append((0, scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    return events


def _type_windows(text: str) -> bool:
    events = build_type_events(text)
    if not events:
        return True
    user32 = ctypes.windll.user32
    arr = (_INPUT * len(events))(
        *(
            _INPUT(type=INPUT_KEYBOARD, ki=_KEYBDINPUT(vk, scan, flags, 0, None))
            for vk, scan, flags in events
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
        ("xdotool", ["type", "--clearmodifiers", "--delay", _XDOTOOL_TYPE_DELAY_MS, "--", text]),
        ("wtype", ["--", text]),
    ):
        path = shutil.which(name)
        if not path:
            continue
        found_tool = True
        timeout = type_timeout_s(len(text))
        result = subprocess.run([path, *args], check=False, timeout=timeout)
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
    """`combo` tuş bileşimini ön plandaki pencereye gönderir; başarılıysa True döner.

    Hata yükseltmez: araç yoksa ya da gönderim başarısızsa False. `sender` testler için
    enjekte edilebilir (verilirse çağrılır ve True döner)."""
    if sender is not None:
        sender()
        return True
    try:
        return _send_windows(combo) if sys.platform == "win32" else _send_linux(combo)
    except (OSError, subprocess.SubprocessError) as exc:
        log.error("yapıştırma tuşu gönderilemedi: %s", exc)
        return False


def type_unicode_text(text: str, sender: Callable[[str], bool] | None = None) -> bool:
    """Metni panoyu kullanmadan karakter karakter yazar (profildeki "Tuş tuş yaz" modu).

    Windows'ta SendInput Unicode (satır sonu = Shift+Enter), Linux'ta `xdotool type`
    ya da `wtype`. Başarılıysa True; hata yükseltmez."""
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
    """Ön plandaki pencere Dikte'nin kendisi değilse yapıştırır; yapıştırdıysa True döner.

    Pencere kimliği yalnızca Windows'ta bilinir; Linux'ta denetim yapılmadan gönderilir."""
    foreground = foreground_window_id()
    if foreground is not None and foreground in own_win_ids:
        return False
    return send_paste_keystroke(sender, combo=combo)
