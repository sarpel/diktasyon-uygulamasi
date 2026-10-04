from dikte.platform.foreground import foreground_process_name


def test_uses_probe_result_lowercased():
    assert foreground_process_name(probe=lambda: "Code.exe") == "code.exe"


def test_probe_exception_returns_empty_string():
    def failing_probe():
        raise OSError("boom")

    assert foreground_process_name(probe=failing_probe) == ""


def test_probe_empty_result_returns_empty_string():
    assert foreground_process_name(probe=lambda: "") == ""


def test_default_probe_on_unsupported_platform_returns_empty_string(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "darwin")
    assert foreground_process_name() == ""


def test_linux_process_name_prefers_exe_basename(tmp_path):
    from dikte.platform.foreground import linux_process_name

    proc = tmp_path / "42"
    proc.mkdir()
    (proc / "comm").write_text("gnome-terminal-\n", encoding="utf-8")
    (proc / "exe").symlink_to("/usr/libexec/gnome-terminal-server")
    assert linux_process_name("42", proc_root=tmp_path) == "gnome-terminal-server"


def test_linux_process_name_falls_back_to_cmdline(tmp_path):
    from dikte.platform.foreground import linux_process_name

    proc = tmp_path / "42"
    proc.mkdir()
    (proc / "comm").write_text("gnome-terminal-\n", encoding="utf-8")
    (proc / "cmdline").write_bytes(b"/usr/libexec/gnome-terminal-server\x00--foo\x00")
    assert linux_process_name("42", proc_root=tmp_path) == "gnome-terminal-server"


def test_linux_process_name_falls_back_to_comm(tmp_path):
    from dikte.platform.foreground import linux_process_name

    proc = tmp_path / "42"
    proc.mkdir()
    (proc / "comm").write_text("kate\n", encoding="utf-8")
    (proc / "cmdline").write_bytes(b"")
    assert linux_process_name("42", proc_root=tmp_path) == "kate"


def test_linux_probe_uses_injected_runner(tmp_path):
    from dikte.platform.foreground import _linux_probe

    proc = tmp_path / "7"
    proc.mkdir()
    (proc / "comm").write_text("kate\n", encoding="utf-8")
    outputs = {"getactivewindow": "123\n", "getwindowpid": "7\n"}

    def run(args):
        return outputs[args[1]]

    assert _linux_probe(run=run, proc_root=tmp_path) == "kate"


def test_linux_process_name_keeps_short_comm_for_interpreted_apps(tmp_path):
    from dikte.platform.foreground import linux_process_name

    proc = tmp_path / "42"
    proc.mkdir()
    (proc / "comm").write_text("terminator\n", encoding="utf-8")
    (proc / "exe").symlink_to("/usr/bin/python3.12")
    assert linux_process_name("42", proc_root=tmp_path) == "terminator"


WAYLAND_ENV = {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}


def _fail_if_xdotool_called(monkeypatch):
    from dikte.platform import foreground

    def boom(args):
        raise AssertionError("Wayland'de xdotool'un etkin penceresine güvenilmemeli")

    monkeypatch.setattr(foreground, "_run_xdotool", boom)
    monkeypatch.setattr(foreground.sys, "platform", "linux")


def test_wayland_foreground_is_unknown_not_xdotool_guess(monkeypatch):
    """Wayland'de xdotool yalnızca XWayland pencerelerini görür; etkin pencere sanılan
    pencere yanlış olabilir. Sonuç "bilinmiyor" (None) olmalı, sessizce "profil yok" değil."""
    from dikte.platform.foreground import probe_foreground_process

    _fail_if_xdotool_called(monkeypatch)
    assert probe_foreground_process(env=WAYLAND_ENV) is None


def test_wayland_foreground_name_stays_backward_compatible(monkeypatch):
    _fail_if_xdotool_called(monkeypatch)
    assert foreground_process_name(env=WAYLAND_ENV) == ""


def test_probe_foreground_process_returns_lowercased_name():
    from dikte.platform.foreground import probe_foreground_process

    assert probe_foreground_process(probe=lambda: "Code.exe") == "code.exe"


def test_probe_foreground_process_unknown_on_error_or_empty():
    from dikte.platform.foreground import probe_foreground_process

    def failing():
        raise OSError("xdotool yok")

    assert probe_foreground_process(probe=failing) is None
    assert probe_foreground_process(probe=lambda: "  ") is None


def test_x11_foreground_still_uses_xdotool(monkeypatch, tmp_path):
    from dikte.platform import foreground

    proc = tmp_path / "7"
    proc.mkdir()
    (proc / "comm").write_text("kate\n", encoding="utf-8")
    outputs = {"getactivewindow": "123\n", "getwindowpid": "7\n"}
    monkeypatch.setattr(foreground, "_run_xdotool", lambda args: outputs[args[1]])
    monkeypatch.setattr(foreground, "_PROC_ROOT", tmp_path)
    monkeypatch.setattr(foreground.sys, "platform", "linux")
    env = {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}
    assert foreground.probe_foreground_process(env=env) == "kate"


def test_unknown_foreground_hint_is_turkish():
    from dikte.platform.foreground import FOREGROUND_UNKNOWN_MESSAGE

    assert "Wayland" in FOREGROUND_UNKNOWN_MESSAGE
    assert "profil" in FOREGROUND_UNKNOWN_MESSAGE
