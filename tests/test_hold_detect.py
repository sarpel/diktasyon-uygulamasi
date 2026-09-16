from dikte.platform.hold_detect import HoldDetector


def _collect(d):
    got = []
    d.held.connect(lambda: got.append("held"))
    d.released.connect(lambda: got.append("released"))
    d.tapped.connect(lambda: got.append("tapped"))
    return got


def test_short_press_emits_tapped(qtbot):
    d = HoldDetector(key_probe=lambda vk: False, hold_ms=100, poll_ms=10)
    got = _collect(d)
    d.arm(0x20)
    qtbot.waitUntil(lambda: got == ["tapped"], timeout=1000)
    assert not d.armed


def test_long_press_emits_held_then_released(qtbot):
    state = {"down": True}
    d = HoldDetector(key_probe=lambda vk: state["down"], hold_ms=60, poll_ms=10)
    got = _collect(d)
    d.arm(0x20)
    qtbot.waitUntil(lambda: got == ["held"], timeout=1000)
    state["down"] = False
    qtbot.waitUntil(lambda: got == ["held", "released"], timeout=1000)


def test_arm_while_armed_is_ignored(qtbot):
    d = HoldDetector(key_probe=lambda vk: True, hold_ms=1000, poll_ms=10)
    d.arm(0x20)
    d.arm(0x21)
    assert d._vk == 0x20
