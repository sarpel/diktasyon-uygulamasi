import uuid

from dikte.platform.single_instance import (
    START_MESSAGE,
    STOP_MESSAGE,
    TOGGLE_MESSAGE,
    SingleInstance,
    send_command,
)


def test_first_instance_acquires_and_second_is_rejected(qtbot):
    name = f"dikte-test-{uuid.uuid4().hex[:8]}"
    first = SingleInstance(name)
    assert first.try_acquire() is True

    activations = []
    first.activated.connect(lambda: activations.append(True))

    second = SingleInstance(name)
    assert second.try_acquire() is False
    qtbot.waitUntil(lambda: bool(activations), timeout=2000)


def test_acquire_is_independent_per_name(qtbot):
    a = SingleInstance(f"dikte-test-{uuid.uuid4().hex[:8]}")
    b = SingleInstance(f"dikte-test-{uuid.uuid4().hex[:8]}")
    assert a.try_acquire() and b.try_acquire()


def test_toggle_message_emits_toggle_requested(qtbot):
    name = f"dikte-test-{uuid.uuid4().hex[:8]}"
    inst = SingleInstance(name)
    assert inst.try_acquire() is True
    toggles = []
    inst.toggle_requested.connect(toggles.append)
    assert send_command(name, TOGGLE_MESSAGE) is True
    assert toggles == ["correct"]


def test_toggle_message_with_mode_suffix_carries_mode(qtbot):
    name = f"dikte-test-{uuid.uuid4().hex[:8]}"
    inst = SingleInstance(name)
    assert inst.try_acquire() is True
    toggles = []
    inst.toggle_requested.connect(toggles.append)
    assert send_command(name, TOGGLE_MESSAGE + b":translate") is True
    assert toggles == ["translate"]


def test_start_message_emits_start_requested(qtbot):
    name = f"dikte-test-{uuid.uuid4().hex[:8]}"
    inst = SingleInstance(name)
    assert inst.try_acquire() is True
    starts = []
    inst.start_requested.connect(starts.append)
    assert send_command(name, START_MESSAGE + b":prompt") is True
    assert starts == ["prompt"]


def test_stop_message_emits_stop_requested(qtbot):
    name = f"dikte-test-{uuid.uuid4().hex[:8]}"
    inst = SingleInstance(name)
    assert inst.try_acquire() is True
    stops = []
    inst.stop_requested.connect(lambda: stops.append(True))
    assert send_command(name, STOP_MESSAGE) is True
    assert stops == [True]
