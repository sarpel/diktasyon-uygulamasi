import uuid

from dikte.platform.single_instance import SingleInstance


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
