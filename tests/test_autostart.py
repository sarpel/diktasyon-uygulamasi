from dikte.platform.autostart import RUN_KEY, VALUE_NAME, is_autostart_enabled, set_autostart


class FakeReg:
    """winreg'in kullanılan alt kümesi."""

    def __init__(self):
        self.values = {}

    def set_value(self, key, name, value):
        self.values[(key, name)] = value

    def get_value(self, key, name):
        return self.values.get((key, name))

    def delete_value(self, key, name):
        self.values.pop((key, name), None)


def test_enable_writes_run_value():
    r = FakeReg()
    set_autostart(True, exe_path=r"C:\Apps\Dikte\Dikte.exe", reg=r)
    assert r.values[(RUN_KEY, VALUE_NAME)] == '"C:\\Apps\\Dikte\\Dikte.exe" --minimized'
    assert is_autostart_enabled(reg=r)


def test_disable_removes_value():
    r = FakeReg()
    set_autostart(True, exe_path="x.exe", reg=r)
    set_autostart(False, reg=r)
    assert not is_autostart_enabled(reg=r)


def test_disable_when_absent_is_noop():
    r = FakeReg()
    set_autostart(False, reg=r)
    assert not is_autostart_enabled(reg=r)


def test_xdg_autostart_writes_desktop_file(tmp_path):
    from dikte.platform.autostart import _XdgAutostart

    path = tmp_path / "autostart" / "dikte.desktop"
    x = _XdgAutostart(path)
    set_autostart(True, exe_path="/usr/bin/dikte", reg=x)
    assert path.exists()
    body = path.read_text(encoding="utf-8")
    assert body.startswith("[Desktop Entry]")
    assert "Exec=/usr/bin/dikte --minimized" in body
    assert "Name=Dikte" in body
    assert is_autostart_enabled(reg=x)


def test_xdg_autostart_disable_removes_file(tmp_path):
    from dikte.platform.autostart import _XdgAutostart

    path = tmp_path / "autostart" / "dikte.desktop"
    x = _XdgAutostart(path)
    set_autostart(True, exe_path="/usr/bin/dikte", reg=x)
    set_autostart(False, reg=x)
    assert not path.exists()
    assert not is_autostart_enabled(reg=x)


def test_xdg_autostart_disable_when_absent_is_noop(tmp_path):
    from dikte.platform.autostart import _XdgAutostart

    x = _XdgAutostart(tmp_path / "yok.desktop")
    set_autostart(False, reg=x)
    assert not is_autostart_enabled(reg=x)


def test_launch_command_uses_interpreter_off_windows(monkeypatch):
    from dikte.platform import autostart as a

    monkeypatch.setattr(a.sys, "platform", "linux")
    monkeypatch.setattr(a.sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(a.sys, "frozen", False, raising=False)
    assert a.launch_command() == "/usr/bin/python3 -m dikte --minimized"


def test_default_backend_off_windows_is_xdg(monkeypatch):
    from dikte.platform import autostart as a

    monkeypatch.setattr(a.sys, "platform", "linux")
    assert isinstance(a._reg(None), a._XdgAutostart)
