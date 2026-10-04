import ctypes
import subprocess
from types import SimpleNamespace

import pytest

from dikte.platform import paste


def test_input_struct_matches_win32_abi():
    """SendInput cbSize == sizeof(INPUT) şartını koşuyor (Microsoft belgeleri); yanlış
    boyut hiçbir tuş vuruşu göndermeden sessizce başarısız olur. 64-bit Win32 INPUT
    (DWORD type + union{MOUSEINPUT,KEYBDINPUT,HARDWAREINPUT}) her zaman 40 bayttır."""
    assert ctypes.sizeof(paste._INPUT) == 40
    assert ctypes.sizeof(paste._MOUSEINPUT) == 32
    assert ctypes.sizeof(paste._KEYBDINPUT) == 24
    assert ctypes.sizeof(paste._HARDWAREINPUT) == 8


@pytest.fixture(autouse=True)
def _reset_warning(monkeypatch):
    # Testler X11 oturumu varsayar; geliştiricinin Wayland masaüstü sonucu değiştirmesin.
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    paste._warned.clear()
    paste._warned["tools"] = False
    yield
    paste._warned.clear()
    paste._warned["tools"] = False


def test_paste_skips_when_foreground_is_own_window(monkeypatch):
    monkeypatch.setattr(paste, "foreground_window_id", lambda: 42)
    sent = []
    assert paste.paste_active_window({42}, sender=lambda: sent.append(1)) is False
    assert sent == []


def test_paste_sends_keystroke_when_foreground_is_other_window(monkeypatch):
    monkeypatch.setattr(paste, "foreground_window_id", lambda: 7)
    sent = []
    assert paste.paste_active_window({42}, sender=lambda: sent.append(1)) is True
    assert sent == [1]


def test_linux_sender_prefers_xdotool(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(
        paste.shutil, "which", lambda n: "/usr/bin/xdotool" if n == "xdotool" else None
    )
    ran = []
    monkeypatch.setattr(
        paste.subprocess,
        "run",
        lambda cmd, **k: ran.append(cmd) or SimpleNamespace(returncode=0),
    )
    assert paste.send_paste_keystroke() is True
    assert ran and ran[0][0] == "/usr/bin/xdotool"


def test_linux_falls_back_to_wtype(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: "/usr/bin/wtype" if n == "wtype" else None)
    ran = []
    monkeypatch.setattr(
        paste.subprocess,
        "run",
        lambda cmd, **k: ran.append(cmd) or SimpleNamespace(returncode=0),
    )
    assert paste.send_paste_keystroke() is True
    assert ran[0][:2] == ["/usr/bin/wtype", "-M"]


def test_linux_without_tools_returns_false_and_warns_once(monkeypatch, caplog):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: None)
    assert paste.send_paste_keystroke() is False
    assert paste.send_paste_keystroke() is False
    assert caplog.text.count("xdotool") == 1


def test_subprocess_failure_is_reported_not_raised(monkeypatch, caplog):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: "/usr/bin/xdotool")

    def boom(cmd, **kwargs):
        raise OSError("çalıştırılamadı")

    monkeypatch.setattr(paste.subprocess, "run", boom)
    assert paste.send_paste_keystroke() is False
    assert "yapıştırma" in caplog.text.lower()


def test_timeout_is_handled(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: "/usr/bin/xdotool")

    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 3)

    monkeypatch.setattr(paste.subprocess, "run", slow)
    assert paste.send_paste_keystroke() is False


def test_foreground_window_id_is_none_on_linux(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    assert paste.foreground_window_id() is None


def test_failing_xdotool_falls_back_to_wtype(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: f"/usr/bin/{n}")
    ran = []

    def run(cmd, **kwargs):
        ran.append(cmd[0])
        return SimpleNamespace(returncode=0 if cmd[0].endswith("wtype") else 1)

    monkeypatch.setattr(paste.subprocess, "run", run)
    assert paste.send_paste_keystroke() is True
    assert ran == ["/usr/bin/xdotool", "/usr/bin/wtype"]


def test_all_tools_failing_returns_false(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(paste.subprocess, "run", lambda cmd, **k: SimpleNamespace(returncode=1))
    assert paste.send_paste_keystroke() is False


def test_build_key_inputs_presses_then_releases_in_reverse():
    from dikte.platform.paste import KEYEVENTF_KEYUP, VK_CONTROL, VK_SHIFT, VK_V, build_key_inputs

    seq = build_key_inputs((VK_CONTROL, VK_SHIFT, VK_V))
    assert seq[:3] == [(VK_CONTROL, 0), (VK_SHIFT, 0), (VK_V, 0)]
    assert seq[3:] == [
        (VK_V, KEYEVENTF_KEYUP),
        (VK_SHIFT, KEYEVENTF_KEYUP),
        (VK_CONTROL, KEYEVENTF_KEYUP),
    ]


def test_linux_combo_ctrl_shift_v(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(
        paste.shutil, "which", lambda n: "/usr/bin/xdotool" if n == "xdotool" else None
    )
    ran = []
    monkeypatch.setattr(
        paste.subprocess, "run", lambda cmd, **k: ran.append(cmd) or SimpleNamespace(returncode=0)
    )
    assert paste.send_paste_keystroke(combo="ctrl+shift+v") is True
    assert ran[0][-1] == "ctrl+shift+v"


def test_type_unicode_text_uses_injected_sender():
    typed = []
    assert paste.type_unicode_text("merhaba", sender=lambda t: typed.append(t) or True) is True
    assert typed == ["merhaba"]


def test_type_unicode_text_linux_xdotool(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(
        paste.shutil, "which", lambda n: "/usr/bin/xdotool" if n == "xdotool" else None
    )
    ran = []
    monkeypatch.setattr(
        paste.subprocess,
        "run",
        lambda cmd, **k: ran.append((cmd, k)) or SimpleNamespace(returncode=0),
    )
    assert paste.type_unicode_text("çay") is True
    cmd, kwargs = ran[0]
    # Dikte edilen metin /proc/<pid>/cmdline'da görünmesin diye stdin'den verilir.
    assert "çay" not in cmd
    assert cmd[-2:] == ["--file", "-"]
    assert kwargs["input"] == "çay"


def test_type_unicode_text_without_tools_returns_false(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: None)
    assert paste.type_unicode_text("merhaba") is False


def test_paste_active_window_forwards_combo(monkeypatch):
    monkeypatch.setattr(paste, "foreground_window_id", lambda: 7)
    seen = {}

    def fake_send(sender=None, *, combo="ctrl+v"):
        seen["combo"] = combo
        return True

    monkeypatch.setattr(paste, "send_paste_keystroke", fake_send)
    assert paste.paste_active_window({42}, combo="ctrl+shift+v") is True
    assert seen["combo"] == "ctrl+shift+v"


def test_linux_type_uses_fast_delay_and_length_scaled_timeout(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(
        paste.shutil, "which", lambda n: "/usr/bin/xdotool" if n == "xdotool" else None
    )
    calls = []
    monkeypatch.setattr(
        paste.subprocess,
        "run",
        lambda cmd, **k: calls.append((cmd, k)) or SimpleNamespace(returncode=0),
    )
    text = "a" * 2000
    assert paste.type_unicode_text(text) is True
    cmd, kwargs = calls[0]
    assert "--delay" in cmd and cmd[cmd.index("--delay") + 1] == "1"
    assert kwargs["timeout"] > paste.type_timeout_s(10)
    assert kwargs["timeout"] >= 2000 * 0.005


def test_type_timeout_grows_with_length():
    assert paste.type_timeout_s(0) >= 3
    assert paste.type_timeout_s(5000) > paste.type_timeout_s(100)


def test_windows_type_events_send_newline_as_shift_enter():
    events = paste.build_type_events("a\nb")
    shift_enter = [
        (paste.VK_SHIFT, 0, 0),
        (paste.VK_RETURN, 0, 0),
        (paste.VK_RETURN, 0, paste.KEYEVENTF_KEYUP),
        (paste.VK_SHIFT, 0, paste.KEYEVENTF_KEYUP),
    ]
    a, b = ord("a"), ord("b")
    uni, up = paste.KEYEVENTF_UNICODE, paste.KEYEVENTF_UNICODE | paste.KEYEVENTF_KEYUP
    assert events == [(0, a, uni), (0, a, up), *shift_enter, (0, b, uni), (0, b, up)]


def test_windows_type_events_treat_crlf_as_single_newline():
    events = paste.build_type_events("a\r\nb")
    assert sum(1 for vk, _s, f in events if vk == paste.VK_RETURN and f == 0) == 1
    events = paste.build_type_events("a\rb")
    assert sum(1 for vk, _s, f in events if vk == paste.VK_RETURN and f == 0) == 1


def test_windows_type_events_keep_surrogate_pairs():
    events = paste.build_type_events("😀")
    assert [s for _vk, s, f in events if f == paste.KEYEVENTF_UNICODE] == [0xD83D, 0xDE00]


def test_linux_combo_ctrl_z_for_undo(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(
        paste.shutil, "which", lambda n: "/usr/bin/xdotool" if n == "xdotool" else None
    )
    ran = []
    monkeypatch.setattr(
        paste.subprocess, "run", lambda cmd, **k: ran.append(cmd) or SimpleNamespace(returncode=0)
    )
    assert paste.send_paste_keystroke(combo="ctrl+z") is True
    assert ran[0][-1] == "ctrl+z"


def test_windows_ctrl_z_vks():
    assert paste._COMBO_VKS["ctrl+z"] == (paste.VK_CONTROL, paste.VK_Z)


# --- Windows: basılı tutulan değiştirici tuşlar (bas-konuş kısayolu) -------------------


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, dt):
        self.sleeps.append(dt)
        self.now += dt


class FakeUser32:
    """`ctypes.windll.user32` taklidi: GetAsyncKeyState + SendInput."""

    def __init__(self, clock, held=None, sent_result=None):
        self.clock = clock
        self.held = dict(held or {})  # vk → bu ana dek basılı (inf = hiç bırakılmaz)
        self.sent_result = sent_result
        self.calls = []

    def GetAsyncKeyState(self, vk):
        return -32768 if self.clock() < self.held.get(vk, -1) else 0

    def SendInput(self, n, arr, size):
        assert size == ctypes.sizeof(paste._INPUT)
        self.calls.append([(arr[i].ki.wVk, arr[i].ki.wScan, arr[i].ki.dwFlags) for i in range(n)])
        return n if self.sent_result is None else self.sent_result(n)


UP = paste.KEYEVENTF_KEYUP


def _send_win(user32, clock):
    return paste._send_windows("ctrl+v", user32=user32, sleep=clock.sleep, clock=clock)


def test_windows_paste_waits_until_hotkey_modifiers_are_released():
    clock = FakeClock()
    user32 = FakeUser32(clock, held={paste.VK_CONTROL: 0.1, paste.VK_MENU: 0.05})
    assert _send_win(user32, clock) is True
    assert 0.1 <= clock.now < paste._MODIFIER_WAIT_S
    # Kullanıcı bıraktı: yalnızca kendi Ctrl+V'miz gönderilir, ek tuş yok.
    assert [(vk, f) for vk, _s, f in user32.calls[0]] == [
        (paste.VK_CONTROL, 0),
        (paste.VK_V, 0),
        (paste.VK_V, UP),
        (paste.VK_CONTROL, UP),
    ]


def test_windows_paste_releases_still_held_modifiers_after_timeout():
    clock = FakeClock()
    held = {paste.VK_CONTROL: float("inf"), paste.VK_SHIFT: float("inf")}
    user32 = FakeUser32(clock, held=held)
    assert _send_win(user32, clock) is True
    assert clock.now >= paste._MODIFIER_WAIT_S
    events = [(vk, f) for vk, _s, f in user32.calls[0]]
    # Önce basılı kalanlar bırakılır (yeniden basılmaz), sonra Ctrl+V.
    assert sorted(events[:2]) == sorted([(paste.VK_SHIFT, UP), (paste.VK_CONTROL, UP)])
    assert events[2:] == [
        (paste.VK_CONTROL, 0),
        (paste.VK_V, 0),
        (paste.VK_V, UP),
        (paste.VK_CONTROL, UP),
    ]


def test_windows_releasing_alt_or_win_is_masked_to_avoid_menu_or_start():
    """Tek başına Alt/Win bırakmak menü çubuğunu/Başlat menüsünü açar; önce atanmamış bir
    "maske" tuşu basılıp bırakılır."""
    clock = FakeClock()
    user32 = FakeUser32(clock, held={paste.VK_LWIN: float("inf")})
    assert _send_win(user32, clock) is True
    events = [(vk, f) for vk, _s, f in user32.calls[0]]
    assert events[:3] == [(paste.VK_MASK, 0), (paste.VK_MASK, UP), (paste.VK_LWIN, UP)]


def test_windows_type_also_waits_for_modifiers_and_reports_typed():
    clock = FakeClock()
    user32 = FakeUser32(clock, held={paste.VK_CONTROL: float("inf")})
    result = paste._type_windows("a", user32=user32, sleep=clock.sleep, clock=clock)
    assert result is paste.TypeOutcome.TYPED
    events = user32.calls[0]
    assert events[0] == (paste.VK_CONTROL, 0, UP)
    assert [s for _vk, s, _f in events[1:]] == [ord("a"), ord("a")]


def test_windows_type_partial_send_is_reported_as_partial():
    clock = FakeClock()
    user32 = FakeUser32(clock, sent_result=lambda n: n - 2)
    result = paste._type_windows("merhaba", user32=user32, sleep=clock.sleep, clock=clock)
    assert result is paste.TypeOutcome.PARTIAL


def test_windows_type_nothing_sent_is_failed():
    clock = FakeClock()
    user32 = FakeUser32(clock, sent_result=lambda n: 0)
    result = paste._type_windows("merhaba", user32=user32, sleep=clock.sleep, clock=clock)
    assert result is paste.TypeOutcome.FAILED


def test_windows_paste_fails_when_sendinput_blocked():
    clock = FakeClock()
    user32 = FakeUser32(clock, sent_result=lambda n: 0)
    assert _send_win(user32, clock) is False


# --- Linux: Wayland ---------------------------------------------------------------------

WAYLAND_ENV = {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0"}


def _both_tools(monkeypatch, returncodes, stderr=""):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: f"/usr/bin/{n}")
    ran = []

    def run(cmd, **kwargs):
        ran.append((cmd, kwargs))
        name = cmd[0].rsplit("/", 1)[-1]
        return SimpleNamespace(returncode=returncodes[name], stderr=stderr)

    monkeypatch.setattr(paste.subprocess, "run", run)
    return ran


def test_is_wayland_session_detection():
    assert paste.is_wayland_session({"XDG_SESSION_TYPE": "wayland"}) is True
    assert paste.is_wayland_session({"WAYLAND_DISPLAY": "wayland-0"}) is True
    assert paste.is_wayland_session({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}) is False
    assert paste.is_wayland_session({}) is False


def test_wayland_paste_prefers_wtype(monkeypatch):
    ran = _both_tools(monkeypatch, {"wtype": 0, "xdotool": 0})
    assert paste.send_paste_keystroke(env=WAYLAND_ENV) is True
    assert [c[0][0] for c in ran] == ["/usr/bin/wtype"]


def test_wayland_detected_from_os_environ(monkeypatch):
    ran = _both_tools(monkeypatch, {"wtype": 0, "xdotool": 0})
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert paste.send_paste_keystroke() is True
    assert ran[0][0][0] == "/usr/bin/wtype"


def test_wayland_without_virtual_keyboard_reports_not_pasted(monkeypatch, caplog):
    """GNOME sanal klavye protokolünü desteklemez; wtype başarısız olur. XWayland yoksa
    xdotool denenmez ve sonuç "yapıştırılmadı" olur (başarı sanılmaz)."""
    ran = _both_tools(
        monkeypatch,
        {"wtype": 1, "xdotool": 0},
        stderr="Compositor does not support the virtual keyboard protocol",
    )
    assert paste.send_paste_keystroke(env=WAYLAND_ENV) is False
    assert [c[0][0] for c in ran] == ["/usr/bin/wtype"]
    assert "sanal klavye" in caplog.text


def test_wayland_xdotool_fallback_is_not_counted_as_success(monkeypatch, caplog):
    """xdotool Wayland'de yalnızca XWayland pencerelerine ulaşır: çıkış kodu 0 olsa da
    yapıştırma doğrulanamaz. Başarı sayılırsa pano geri yüklenir ve dikte kaybolurdu."""
    ran = _both_tools(monkeypatch, {"wtype": 1, "xdotool": 0})
    env = {**WAYLAND_ENV, "DISPLAY": ":0"}
    assert paste.send_paste_keystroke(env=env) is False
    assert [c[0][0] for c in ran] == ["/usr/bin/wtype", "/usr/bin/xdotool"]
    assert "XWayland" in caplog.text


def test_paste_active_window_forwards_env(monkeypatch):
    ran = _both_tools(monkeypatch, {"wtype": 0, "xdotool": 0})
    assert paste.paste_active_window({42}, env=WAYLAND_ENV) is True
    assert ran[0][0][0] == "/usr/bin/wtype"


def test_wayland_typing_prefers_wtype_from_stdin(monkeypatch):
    ran = _both_tools(monkeypatch, {"wtype": 0, "xdotool": 0})
    assert paste.type_text("gizli metin", env=WAYLAND_ENV) is paste.TypeOutcome.TYPED
    cmd, kwargs = ran[0]
    assert cmd == ["/usr/bin/wtype", "-"]
    assert kwargs["input"] == "gizli metin"


def test_wayland_typing_via_xdotool_is_unverified(monkeypatch):
    _both_tools(monkeypatch, {"wtype": 1, "xdotool": 0})
    env = {**WAYLAND_ENV, "DISPLAY": ":0"}
    assert paste.type_text("merhaba", env=env) is paste.TypeOutcome.UNVERIFIED
    assert paste.type_unicode_text("merhaba", env=env) is False


# --- Linux: zaman aşımı / kısmi yazma ------------------------------------------------------


def test_typing_timeout_is_partial_and_does_not_retry_other_tool(monkeypatch, caplog):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: f"/usr/bin/{n}")
    ran = []

    def run(cmd, **kwargs):
        ran.append(cmd[0])
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(paste.subprocess, "run", run)
    assert paste.type_text("uzun metin") is paste.TypeOutcome.PARTIAL
    # Yarıda kesilen metni ikinci araçla baştan yazmak yinelenmiş metin üretirdi.
    assert ran == ["/usr/bin/xdotool"]
    assert paste.type_unicode_text("uzun metin") is False
    assert "panoda" in caplog.text


def test_type_text_failed_when_no_tools(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: None)
    assert paste.type_text("merhaba") is paste.TypeOutcome.FAILED


def test_type_text_uses_injected_sender():
    assert paste.type_text("a", sender=lambda t: True) is paste.TypeOutcome.TYPED
    assert paste.type_text("a", sender=lambda t: False) is paste.TypeOutcome.FAILED


def test_type_outcome_messages_are_turkish():
    assert "panoda" in paste.TypeOutcome.PARTIAL.user_message
    assert "bir kısmı" in paste.TypeOutcome.PARTIAL.user_message
    assert "panoda" in paste.TypeOutcome.FAILED.user_message
    assert paste.TypeOutcome.TYPED.user_message == ""
