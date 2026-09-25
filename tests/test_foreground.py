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
