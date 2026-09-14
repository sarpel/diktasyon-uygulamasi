import uuid

import pytest

from dikte.platform.single_instance import (
    SHOW_MESSAGE,
    TOGGLE_MESSAGE,
    SingleInstance,
    send_command,
)


@pytest.fixture
def running(qtbot):
    inst = SingleInstance(f"dikte-test-{uuid.uuid4().hex[:8]}")
    assert inst.try_acquire() is True
    return inst


def test_toggle_command_reaches_running_instance(running, qtbot):
    seen = []
    running.toggle_requested.connect(lambda: seen.append("toggle"))
    assert send_command(running.name, TOGGLE_MESSAGE) is True
    qtbot.waitUntil(lambda: seen == ["toggle"], timeout=2000)


def test_show_command_reaches_running_instance(running, qtbot):
    seen = []
    running.activated.connect(lambda: seen.append("show"))
    assert send_command(running.name, SHOW_MESSAGE) is True
    qtbot.waitUntil(lambda: seen == ["show"], timeout=2000)


def test_send_command_returns_false_when_nothing_listens():
    assert send_command(f"dikte-yok-{uuid.uuid4().hex[:8]}", TOGGLE_MESSAGE) is False


def test_unknown_command_is_ignored(running, qtbot):
    seen = []
    running.toggle_requested.connect(lambda: seen.append("toggle"))
    running.activated.connect(lambda: seen.append("show"))
    assert send_command(running.name, b"gecersiz") is True
    qtbot.wait(200)
    assert seen == []
