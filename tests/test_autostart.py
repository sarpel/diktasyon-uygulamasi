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


def test_desktop_exec_quotes_paths_with_spaces_using_double_quotes(monkeypatch):
    from dikte.platform import autostart as a

    cmd = a.launch_command("/home/ayşe/My Apps/dikte", posix=True)
    assert cmd == '"/home/ayşe/My Apps/dikte" --minimized'


def test_desktop_exec_escapes_reserved_characters():
    from dikte.platform.autostart import desktop_exec_arg

    assert desktop_exec_arg("/usr/bin/dikte") == "/usr/bin/dikte"
    assert desktop_exec_arg('/a b/"x"') == '"/a b/\\"x\\""'
    assert desktop_exec_arg("/a$b`c") == '"/a\\$b\\`c"'
    assert desktop_exec_arg("/a\\b") == '"/a\\\\b"'
    assert desktop_exec_arg("/a%b") == "/a%%b"
    assert desktop_exec_arg("/a b%c") == '"/a b%%c"'


def test_desktop_file_applies_string_escape_to_backslashes(tmp_path):
    from dikte.platform.autostart import _XdgAutostart

    path = tmp_path / "dikte.desktop"
    set_autostart(True, exe_path="/a\\b", reg=_XdgAutostart(path))
    assert 'Exec="/a\\\\\\\\b" --minimized' in path.read_text(encoding="utf-8")


def test_hidden_desktop_entry_is_not_enabled(tmp_path):
    from dikte.platform.autostart import _XdgAutostart

    path = tmp_path / "dikte.desktop"
    x = _XdgAutostart(path)
    set_autostart(True, exe_path="/usr/bin/dikte", reg=x)
    path.write_text(path.read_text(encoding="utf-8") + "Hidden=true\n", encoding="utf-8")
    assert not is_autostart_enabled(reg=x)


def test_gnome_disabled_desktop_entry_is_not_enabled(tmp_path):
    from dikte.platform.autostart import _XdgAutostart

    path = tmp_path / "dikte.desktop"
    body = "[Desktop Entry]\nType=Application\nExec=dikte\nX-GNOME-Autostart-enabled=false\n"
    path.write_text(body, encoding="utf-8")
    assert not is_autostart_enabled(reg=_XdgAutostart(path))


def test_set_autostart_failure_raises_actionable_error(caplog):
    import pytest

    from dikte.platform.autostart import AutostartError

    class Broken(FakeReg):
        def set_value(self, key, name, value):
            raise PermissionError("erişim reddedildi")

    with pytest.raises(AutostartError) as info:
        set_autostart(True, exe_path="x.exe", reg=Broken())
    assert isinstance(info.value, RuntimeError)
    assert "Otomatik başlatma" in str(info.value)
    assert "otomatik başlatma ayarlanamadı" in caplog.text
