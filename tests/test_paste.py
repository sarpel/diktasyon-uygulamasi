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
def _reset_warning():
    paste._warned["tools"] = False
    yield
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
        paste.subprocess, "run", lambda cmd, **k: ran.append(cmd) or SimpleNamespace(returncode=0)
    )
    assert paste.type_unicode_text("çay") is True and ran[0][-1] == "çay"


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
