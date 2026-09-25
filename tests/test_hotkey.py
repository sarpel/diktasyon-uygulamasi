import pytest

from dikte.platform import hotkey as hk_mod
from dikte.platform.hotkey import GlobalHotkey
from dikte.platform.hotkey_parse import parse_hotkey


class FakeNative:
    def __init__(self, taken=()):
        self.taken = {(s.modifiers, s.vk) for s in (parse_hotkey(t) for t in taken)}
        self.registered: dict[int, tuple[int, int]] = {}

    def register(self, hotkey_id, modifiers, vk):
        if (modifiers, vk) in self.taken:
            return False
        self.registered[hotkey_id] = (modifiers, vk)
        return True

    def unregister(self, hotkey_id):
        self.registered.pop(hotkey_id, None)

    def last_error(self):
        return 1409  # ERROR_HOTKEY_ALREADY_REGISTERED


@pytest.fixture
def win(monkeypatch):
    monkeypatch.setattr(hk_mod.sys, "platform", "win32")


def test_register_succeeds_with_injected_native(qapp, win):
    native = FakeNative()
    hk = GlobalHotkey(native=native)
    assert hk.register("ctrl+alt+d") is True
    assert hk.label
    spec = parse_hotkey("ctrl+alt+d")
    assert native.registered[hk_mod.HOTKEY_ID] == (spec.modifiers, spec.vk)
    hk.unregister()
    assert native.registered == {}


def test_failed_change_restores_previous_hotkey(qapp, win):
    native = FakeNative(taken=("ctrl+alt+x",))
    hk = GlobalHotkey(native=native)
    assert hk.register("ctrl+alt+d") is True
    old_label = hk.label
    assert hk.register("ctrl+alt+x") is False
    old = parse_hotkey("ctrl+alt+d")
    assert native.registered[hk_mod.HOTKEY_ID] == (old.modifiers, old.vk)
    assert hk.label == old_label
    hk.unregister()


def test_failed_first_registration_leaves_nothing(qapp, win):
    native = FakeNative(taken=("ctrl+alt+x",))
    hk = GlobalHotkey(native=native)
    assert hk.register("ctrl+alt+x") is False
    assert native.registered == {}
    assert hk.label == ""
