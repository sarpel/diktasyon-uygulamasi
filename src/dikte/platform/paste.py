"""Panodaki metni ön plandaki uygulamaya yapıştırır ya da doğrudan yazar.

Windows'ta eski `keybd_event` yerine `SendInput` kullanılır (Unicode giriş de dahil).
Göndermeden önce kullanıcının hâlâ basılı tuttuğu değiştirici tuşların (bas-konuş
kısayolu) bırakılması beklenir; aksi hâlde Ctrl+V, Ctrl+Alt+V gibi başka bir kısayola
dönüşürdü.

Linux'ta X11 için `xdotool`, Wayland için `wtype` gerekir. Wayland oturumunda önce `wtype`
denenir; `xdotool` yalnızca XWayland pencerelerine ulaşabildiğinden orada başarısı
doğrulanamaz ve "yapıştırılmadı" sayılır (metin panoda kalır). GNOME sanal klavye
protokolünü desteklemediğinden orada `wtype` çalışmaz. Araç yoksa yapıştırma/yazma
atlanır (bir uyarı günlüğe yazılır) ve metin panoda kalır.

Doğrudan yazmada metin alt sürecin komut satırına değil stdin'ine verilir: komut satırı
(`/proc/<pid>/cmdline`) aynı makinedeki herkesçe okunabilir.

Tuş bileşimleri: Ctrl+V (varsayılan), Ctrl+Shift+V (terminaller) ve "geri al" sesli komutu
için Ctrl+Z. Bu modül Qt kullanmaz; işlevler bir işçi iş parçacığından çağrılabilir.
"""

from __future__ import annotations

import ctypes
import enum
import logging
import os
import shutil
import struct
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from typing import Any, Literal

log = logging.getLogger(__name__)

VK_CONTROL, VK_SHIFT, VK_V, KEYEVENTF_KEYUP = 0x11, 0x10, 0x56, 0x0002
VK_MENU = 0x12  # Alt
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_Z = 0x5A  # "geri al" sesli komutu Ctrl+Z gönderir
VK_RETURN = 0x0D
# Atanmamış sanal tuş (AutoHotkey'in "menu mask" tuşu da budur): tek başına bırakılan
# Alt menü çubuğunu, Win ise Başlat menüsünü açar; önce bu tuş basılıp bırakılarak
# değiştiricinin "tek başına basıldı" sayılması engellenir.
VK_MASK = 0xE8
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
_PASTE_TIMEOUT_S = 3
# Bas-konuş kısayolunun değiştiricileri bırakılsın diye en çok bu kadar beklenir.
_MODIFIER_WAIT_S = 0.5
_MODIFIER_POLL_S = 0.01
_MODIFIER_VKS = (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN)
_KEY_DOWN_BIT = 0x8000
# xdotool'un varsayılan 12 ms/karakter gecikmesi ~250 karakterden uzun metinleri sabit
# zaman aşımında yarıda kestiriyordu; 1 ms ile yazılır, zaman aşımı uzunlukla ölçeklenir
# (xdotool Unicode karakterler için tuş haritası değiştirdiğinden karakter başına pay
# bırakılır).
_XDOTOOL_TYPE_DELAY_MS = "1"
_TYPE_TIMEOUT_PER_CHAR_S = 0.02
_warned = {"tools": False}

KeyCombo = Literal["ctrl+v", "ctrl+shift+v", "ctrl+z"]
Clock = Callable[[], float]
Sleep = Callable[[float], object]


class TypeOutcome(enum.Enum):
    """Doğrudan yazmanın sonucu. Yalnızca `TYPED` başarıdır; diğerlerinde metin panodadır.

    - `FAILED`: hiçbir şey yazılmadı (araç yok, reddedildi).
    - `PARTIAL`: yazma yarıda kesildi (zaman aşımı / eksik gönderim); hedefte metnin
      bir kısmı olabilir — aynı metni yeniden yazmak yinelemeye yol açar.
    - `UNVERIFIED`: araç başarılı döndü ama hedefe ulaştığı doğrulanamıyor (Wayland'de
      xdotool yalnızca XWayland pencerelerine yazar)."""

    TYPED = "typed"
    FAILED = "failed"
    PARTIAL = "partial"
    UNVERIFIED = "unverified"

    @property
    def user_message(self) -> str:
        """Kullanıcıya gösterilecek Türkçe açıklama; başarıda boş dize."""
        return _TYPE_MESSAGES[self]


_TYPE_MESSAGES: dict[TypeOutcome, str] = {
    TypeOutcome.TYPED: "",
    TypeOutcome.FAILED: "Metin yazılamadı; tamamı panoda, Ctrl+V ile yapıştırabilirsiniz.",
    TypeOutcome.PARTIAL: (
        "Metnin bir kısmı yazılamadı; tamamı panoda. Yazılan kısmı silip Ctrl+V ile "
        "yapıştırabilirsiniz."
    ),
    TypeOutcome.UNVERIFIED: (
        "Metnin yazıldığı doğrulanamadı (Wayland); tamamı panoda, gerekirse Ctrl+V ile yapıştırın."
    ),
}

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


def is_wayland_session(env: Mapping[str, str] | None = None) -> bool:
    """Oturum Wayland mı? `XDG_SESSION_TYPE=wayland` ya da `WAYLAND_DISPLAY` tanımlıysa."""
    env = os.environ if env is None else env
    return env.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(env.get("WAYLAND_DISPLAY"))


def build_key_inputs(vks: tuple[int, ...]) -> list[tuple[int, int]]:
    """Verilen sanal tuşlar için önce sırayla bas, sonra ters sırayla bırak listesi üretir."""
    return [(vk, 0) for vk in vks] + [(vk, KEYEVENTF_KEYUP) for vk in reversed(vks)]


def _windows_user32() -> Any:
    user32 = ctypes.windll.user32
    # GetAsyncKeyState SHORT döndürür; varsayılan int dönüşü üst bitleri belirsiz bırakır.
    user32.GetAsyncKeyState.restype = ctypes.c_short
    return user32


def _held_modifiers(user32: Any) -> list[int]:
    return [vk for vk in _MODIFIER_VKS if user32.GetAsyncKeyState(vk) & _KEY_DOWN_BIT]


def release_events_for_held_modifiers(
    user32: Any,
    *,
    sleep: Sleep = time.sleep,
    clock: Clock = time.monotonic,
    timeout_s: float = _MODIFIER_WAIT_S,
) -> list[tuple[int, int, int]]:
    """Kullanıcının basılı tuttuğu değiştiricilerin bırakılmasını `timeout_s` kadar bekler.

    Bas-konuş kısayolunda (ör. Ctrl+Alt basılı) sonuç tuşlar hâlâ basılıyken gelebilir;
    o an gönderilen Ctrl+V uygulamaya Ctrl+Alt+V olarak ulaşırdı. Süre dolunca hâlâ basılı
    olanlar için (wVk, wScan, dwFlags) biçiminde "bırak" olayları döner; çağıran bunları
    yapıştırmadan önce gönderir (yeniden basılmaz: fiziksel bırakma zararsız bir fazladan
    "bırak" olur). Alt/Win bırakılacaksa menü/Başlat açılmasın diye önce maske tuşu eklenir."""
    deadline = clock() + timeout_s
    held = _held_modifiers(user32)
    while held and clock() < deadline:
        sleep(_MODIFIER_POLL_S)
        held = _held_modifiers(user32)
    if not held:
        return []
    log.info("değiştirici tuşlar hâlâ basılı (%s); yapıştırmadan önce bırakılıyor", held)
    events: list[tuple[int, int, int]] = []
    if any(vk in (VK_MENU, VK_LWIN, VK_RWIN) for vk in held):
        events += [(VK_MASK, 0, 0), (VK_MASK, 0, KEYEVENTF_KEYUP)]
    events += [(vk, 0, KEYEVENTF_KEYUP) for vk in held]
    return events


def _send_input(user32: Any, events: list[tuple[int, int, int]]) -> int:
    arr = (_INPUT * len(events))(
        *(
            _INPUT(type=INPUT_KEYBOARD, ki=_KEYBDINPUT(vk, scan, flags, 0, None))
            for vk, scan, flags in events
        )
    )
    return int(user32.SendInput(len(arr), arr, ctypes.sizeof(_INPUT)))


def _send_windows(
    combo: KeyCombo = "ctrl+v",
    *,
    user32: Any = None,
    sleep: Sleep = time.sleep,
    clock: Clock = time.monotonic,
) -> bool:
    user32 = _windows_user32() if user32 is None else user32
    prefix = release_events_for_held_modifiers(user32, sleep=sleep, clock=clock)
    events = prefix + [(vk, 0, flags) for vk, flags in build_key_inputs(_COMBO_VKS[combo])]
    return _send_input(user32, events) == len(events)


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


def _type_windows(
    text: str,
    *,
    user32: Any = None,
    sleep: Sleep = time.sleep,
    clock: Clock = time.monotonic,
) -> TypeOutcome:
    body = build_type_events(text)
    if not body:
        return TypeOutcome.TYPED
    user32 = _windows_user32() if user32 is None else user32
    prefix = release_events_for_held_modifiers(user32, sleep=sleep, clock=clock)
    events = prefix + body
    sent = _send_input(user32, events)
    if sent == len(events):
        return TypeOutcome.TYPED
    if sent <= len(prefix):
        log.warning("SendInput hiçbir karakteri iletmedi (hedef yükseltilmiş olabilir)")
        return TypeOutcome.FAILED
    log.warning("SendInput yazmayı yarıda kesti: %d/%d olay", sent, len(events))
    return TypeOutcome.PARTIAL


def _linux_tools(
    wayland: bool, env: Mapping[str, str], tools: list[tuple[str, list[str]]]
) -> list[tuple[str, list[str]]]:
    """Araçları oturuma göre sıralar. Wayland'de wtype önce gelir; xdotool yalnızca XWayland
    varsa (DISPLAY tanımlı) denenir. `tools` X11 sırasıyla (xdotool, wtype) verilir."""
    if not wayland:
        return tools
    ordered = list(reversed(tools))
    return [(n, a) for n, a in ordered if n != "xdotool" or env.get("DISPLAY")]


def _run_tool(path: str, args: list[str], timeout: float, stdin_text: str | None = None) -> Any:
    return subprocess.run(
        [path, *args],
        check=False,
        timeout=timeout,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=stdin_text,
    )


def _log_tool_failure(name: str, action: str, result: Any) -> None:
    stderr = str(getattr(result, "stderr", "") or "").strip()
    log.warning(
        "%s %s komutu başarısız (çıkış kodu %s): %s", name, action, result.returncode, stderr
    )
    if name == "wtype" and "virtual keyboard" in stderr and not _warned.get("vk"):
        log.warning(
            "bu Wayland bileşimcisi sanal klavye protokolünü desteklemiyor (ör. GNOME); "
            "otomatik yapıştırma yapılamıyor, metin panoda kaldı — Ctrl+V ile yapıştırın"
        )
        _warned["vk"] = True


def _warn_xwayland_unverified() -> None:
    if not _warned.get("xwayland"):
        log.warning(
            "Wayland oturumunda xdotool yalnızca XWayland pencerelerine ulaşır; "
            "yapıştırma doğrulanamadı, metin panoda kaldı"
        )
        _warned["xwayland"] = True


def _warn_no_tools(wayland: bool, action: str) -> None:
    if _warned["tools"]:
        return
    tools = (
        "wtype (Wayland) veya xdotool (X11)" if wayland else "xdotool (X11) veya wtype (Wayland)"
    )
    log.warning("otomatik %s için %s gerekli; metin panoda kaldı", action, tools)
    _warned["tools"] = True


def _send_linux(combo: KeyCombo = "ctrl+v", *, env: Mapping[str, str] | None = None) -> bool:
    """X11'de önce xdotool, Wayland'de önce wtype; ilki başarısızsa diğeri denenir."""
    env = os.environ if env is None else env
    wayland = is_wayland_session(env)
    found_tool = False
    for name, args in _linux_tools(
        wayland,
        env,
        [("xdotool", ["key", "--clearmodifiers", combo]), ("wtype", _WTYPE_ARGS[combo])],
    ):
        path = shutil.which(name)
        if not path:
            continue
        found_tool = True
        result = _run_tool(path, args, _PASTE_TIMEOUT_S)
        if result.returncode != 0:
            _log_tool_failure(name, "yapıştırma", result)
            continue
        if wayland and name == "xdotool":
            _warn_xwayland_unverified()
            return False
        return True
    if not found_tool:
        _warn_no_tools(wayland, "yapıştırma")
    return False


def _type_linux(text: str, *, env: Mapping[str, str] | None = None) -> TypeOutcome:
    """Metni doğrudan yazar (X11'de önce xdotool, Wayland'de önce wtype); metin stdin'den
    verilir. Zaman aşımında süreç yarıda öldürülür: `PARTIAL` döner ve ikinci araç
    denenmez (metnin baştan yeniden yazılması yineleme üretirdi)."""
    env = os.environ if env is None else env
    wayland = is_wayland_session(env)
    found_tool = False
    xdotool_args = ["type", "--clearmodifiers", "--delay", _XDOTOOL_TYPE_DELAY_MS, "--file", "-"]
    for name, args in _linux_tools(wayland, env, [("xdotool", xdotool_args), ("wtype", ["-"])]):
        path = shutil.which(name)
        if not path:
            continue
        found_tool = True
        try:
            result = _run_tool(path, args, type_timeout_s(len(text)), stdin_text=text)
        except subprocess.TimeoutExpired:
            log.warning(
                "%s yazması zaman aşımına uğradı; metnin bir kısmı yazılamadı, tamamı panoda",
                name,
            )
            return TypeOutcome.PARTIAL
        if result.returncode != 0:
            _log_tool_failure(name, "yazma", result)
            continue
        if wayland and name == "xdotool":
            _warn_xwayland_unverified()
            return TypeOutcome.UNVERIFIED
        return TypeOutcome.TYPED
    if not found_tool:
        _warn_no_tools(wayland, "yazma")
    return TypeOutcome.FAILED


def send_paste_keystroke(
    sender: Callable[[], object] | None = None,
    *,
    combo: KeyCombo = "ctrl+v",
    env: Mapping[str, str] | None = None,
) -> bool:
    """`combo` tuş bileşimini ön plandaki pencereye gönderir; başarılıysa True döner.

    Hata yükseltmez: araç yoksa ya da gönderim başarısızsa/doğrulanamıyorsa False.
    `sender` testler için enjekte edilebilir (verilirse çağrılır ve True döner); `env`
    Linux'ta oturum türünü (X11/Wayland) belirlemek içindir, varsayılan `os.environ`."""
    if sender is not None:
        sender()
        return True
    try:
        return _send_windows(combo) if sys.platform == "win32" else _send_linux(combo, env=env)
    except (OSError, subprocess.SubprocessError):
        log.exception("yapıştırma tuşu gönderilemedi; metin panoda kaldı")
        return False


def type_text(
    text: str,
    sender: Callable[[str], bool] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> TypeOutcome:
    """Metni panoyu kullanmadan karakter karakter yazar ve ayrıntılı sonucu döndürür.

    Windows'ta SendInput Unicode (satır sonu = Shift+Enter), Linux'ta `xdotool type` ya da
    `wtype`. Hata yükseltmez. Qt kullanmaz; uzun metinlerde GUI'yi bekletmemek için bir
    işçi iş parçacığından çağrılabilir. Başarısızlıkta `TypeOutcome.user_message`
    kullanıcıya gösterilebilir."""
    if sender is not None:
        return TypeOutcome.TYPED if sender(text) else TypeOutcome.FAILED
    try:
        return _type_windows(text) if sys.platform == "win32" else _type_linux(text, env=env)
    except (OSError, subprocess.SubprocessError):
        log.exception("metin yazılamadı; metin panoda kaldı")
        return TypeOutcome.FAILED


def type_unicode_text(
    text: str,
    sender: Callable[[str], bool] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Geriye dönük uyumlu sarmalayıcı: yalnızca tamamı yazıldıysa True (bkz. `type_text`)."""
    return type_text(text, sender, env=env) is TypeOutcome.TYPED


def paste_active_window(
    own_win_ids: set[int],
    sender: Callable[[], object] | None = None,
    *,
    combo: KeyCombo = "ctrl+v",
    env: Mapping[str, str] | None = None,
) -> bool:
    """Ön plandaki pencere Dikte'nin kendisi değilse yapıştırır; yapıştırdıysa True döner.

    Pencere kimliği yalnızca Windows'ta bilinir; Linux'ta denetim yapılmadan gönderilir."""
    foreground = foreground_window_id()
    if foreground is not None and foreground in own_win_ids:
        return False
    if env is None:
        return send_paste_keystroke(sender, combo=combo)
    return send_paste_keystroke(sender, combo=combo, env=env)
