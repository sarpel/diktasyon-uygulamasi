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
