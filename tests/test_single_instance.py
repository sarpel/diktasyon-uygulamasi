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


def test_default_name_differs_per_user():
    from dikte.platform.single_instance import default_server_name

    a = default_server_name(platform="win32", env={}, user_probe=lambda: "ayse")
    b = default_server_name(platform="win32", env={}, user_probe=lambda: "mehmet")
    assert a != b
    assert a == default_server_name(platform="win32", env={}, user_probe=lambda: "ayse")
    assert a.startswith("dikte-single-instance-")


def test_default_name_on_linux_uses_private_runtime_dir(tmp_path):
    from dikte.platform.single_instance import default_server_name

    name = default_server_name(
        platform="linux", env={"XDG_RUNTIME_DIR": str(tmp_path)}, user_probe=lambda: "ayse"
    )
    assert name == str(tmp_path / "dikte-single-instance")


def test_default_name_on_linux_without_runtime_dir_falls_back_to_user_hash(tmp_path):
    from dikte.platform.single_instance import default_server_name

    missing = str(tmp_path / "yok")
    name = default_server_name(
        platform="linux", env={"XDG_RUNTIME_DIR": missing}, user_probe=lambda: "ayse"
    )
    assert name.startswith("dikte-single-instance-") and "/" not in name


def test_default_name_survives_user_probe_failure():
    from dikte.platform.single_instance import default_server_name

    def boom():
        raise OSError("kullanıcı yok")

    assert default_server_name(platform="win32", env={}, user_probe=boom).startswith(
        "dikte-single-instance-"
    )


def test_server_restricts_access_to_current_user(qtbot):
    from PySide6.QtNetwork import QLocalServer

    inst = SingleInstance(f"dikte-test-{uuid.uuid4().hex[:8]}")
    assert inst.try_acquire() is True
    assert inst._server is not None
    opts = inst._server.socketOptions()
    assert opts & QLocalServer.SocketOption.UserAccessOption


def test_full_path_name_works_for_ipc(qtbot, tmp_path):
    name = str(tmp_path / "dikte-single-instance")
    inst = SingleInstance(name)
    assert inst.try_acquire() is True
    stops = []
    inst.stop_requested.connect(lambda: stops.append(True))
    assert send_command(name, STOP_MESSAGE) is True
    assert stops == [True]
