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
