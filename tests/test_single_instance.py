import os
import socket
import stat
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

    tmp_path.chmod(0o700)
    name = default_server_name(
        platform="linux", env={"XDG_RUNTIME_DIR": str(tmp_path)}, user_probe=lambda: "ayse"
    )
    assert name == str(tmp_path / "dikte-single-instance")


def _uid():
    return os.getuid()


def test_default_name_on_linux_without_runtime_dir_uses_private_tmp_dir(tmp_path):
    """Eskiden ad /tmp altında kullanıcı adının özetiydi: tahmin edilebilir, başka bir
    kullanıcı önceden kapabilirdi. Artık kullanıcıya özel 0700 bir dizin kullanılır."""
    from dikte.platform.single_instance import default_server_name

    missing = str(tmp_path / "yok")
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    name = default_server_name(
        platform="linux",
        env={"XDG_RUNTIME_DIR": missing},
        uid_probe=_uid,
        tempdir=str(tmp),
        home=tmp_path / "ev",
    )
    private = tmp / f"dikte-{_uid()}"
    assert name == str(private / "dikte-single-instance")
    assert stat.S_IMODE(private.stat().st_mode) == 0o700


def test_default_name_ignores_world_readable_runtime_dir(tmp_path):
    from dikte.platform.single_instance import default_server_name

    runtime = tmp_path / "run"
    runtime.mkdir()
    runtime.chmod(0o755)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    name = default_server_name(
        platform="linux",
        env={"XDG_RUNTIME_DIR": str(runtime)},
        uid_probe=_uid,
        tempdir=str(tmp),
        home=tmp_path / "ev",
    )
    assert not name.startswith(str(runtime))


def test_default_name_refuses_squatted_tmp_dir_and_uses_home(tmp_path, caplog):
    """Başka bir kullanıcı /tmp/dikte-<uid> dizinini önceden oluşturduysa (sahibi biz
    değiliz) kullanılmaz; ev dizinindeki özel dizine geçilir."""
    from dikte.platform import single_instance as si

    tmp = tmp_path / "tmp"
    tmp.mkdir()
    squatted = tmp / "dikte-4242"
    squatted.mkdir(mode=0o700)
    home = tmp_path / "ev"
    owners = {str(squatted): 9999}  # dizin başka kullanıcıya ait görünsün

    name = si.default_server_name(
        platform="linux",
        env={},
        uid_probe=lambda: 4242,
        tempdir=str(tmp),
        home=home,
        owner_probe=lambda p: owners.get(str(p), 4242),
    )
    assert name == str(home / ".cache" / "dikte" / "dikte-single-instance")
    assert "kullanılmıyor" in caplog.text


def test_unix_peer_uid_reads_so_peercred():
    from dikte.platform.single_instance import unix_peer_uid

    a, b = socket.socketpair()
    try:
        assert unix_peer_uid(a.fileno(), "") == os.getuid()
    finally:
        a.close()
        b.close()


def test_unix_peer_verifier_rejects_other_user():
    from dikte.platform.single_instance import unix_peer_is_current_user

    a, b = socket.socketpair()
    try:
        assert unix_peer_is_current_user(a.fileno(), "", uid_probe=os.getuid) is True
        assert unix_peer_is_current_user(a.fileno(), "", uid_probe=lambda: 99999) is False
    finally:
        a.close()
        b.close()


class FakeWinApi:
    def __init__(self, server_pid: int | None = 1234, sids=None, current="S-1-5-21-1"):
        self.server_pid_value = server_pid
        self.sids = {1234: "S-1-5-21-1"} if sids is None else sids
        self.current = current

    def server_pid(self, handle):
        return self.server_pid_value

    def process_user_sid(self, pid):
        return self.sids.get(pid)

    def current_user_sid(self):
        return self.current


def test_windows_peer_same_user_is_trusted():
    from dikte.platform.single_instance import windows_peer_is_current_user

    assert windows_peer_is_current_user(77, api=FakeWinApi()) is True


def test_windows_peer_other_user_is_untrusted():
    from dikte.platform.single_instance import windows_peer_is_current_user

    api = FakeWinApi(sids={1234: "S-1-5-21-2"})
    assert windows_peer_is_current_user(77, api=api) is False


def test_windows_peer_unverifiable_is_none():
    from dikte.platform.single_instance import windows_peer_is_current_user

    assert windows_peer_is_current_user(77, api=FakeWinApi(server_pid=None)) is None
    assert windows_peer_is_current_user(77, api=FakeWinApi(sids={})) is None


def test_send_command_refuses_unverified_server(qtbot, caplog):
    name = f"dikte-test-{uuid.uuid4().hex[:8]}"
    inst = SingleInstance(name)
    assert inst.try_acquire() is True
    toggles = []
    inst.toggle_requested.connect(toggles.append)
    assert send_command(name, TOGGLE_MESSAGE, peer_verifier=lambda d, n: False) is False
    assert send_command(name, TOGGLE_MESSAGE, peer_verifier=lambda d, n: None) is False
    qtbot.wait(50)
    assert toggles == []
    assert "doğrulan" in caplog.text


def test_squatted_name_does_not_make_dikte_exit(qtbot):
    """Başka bir kullanıcının sunucusu adı tutuyorsa Dikte kapanmamalı (eskiden "zaten
    çalışıyor" sanıp çıkıyordu); IPC'siz sürer ve kullanıcıya Türkçe uyarı verilir."""
    from dikte.platform.single_instance import IpcStatus

    name = f"dikte-test-{uuid.uuid4().hex[:8]}"
    squatter = SingleInstance(name)
    assert squatter.try_acquire() is True
    shown = []
    squatter.activated.connect(lambda: shown.append(True))

    me = SingleInstance(name, peer_verifier=lambda d, n: False)
    assert me.try_acquire() is True
    assert me.status is IpcStatus.UNTRUSTED
    assert me.warning_message and "başka bir kullanıcı" in me.warning_message
    qtbot.wait(50)
    assert shown == []


def test_listen_failure_is_reported_with_turkish_warning(qtbot, tmp_path):
    from dikte.platform.single_instance import IpcStatus

    inst = SingleInstance(str(tmp_path / "olmayan-dizin" / "soket"))
    assert inst.try_acquire() is True  # kilit kurulamasa da uygulama çalışır
    assert inst.status is IpcStatus.UNAVAILABLE
    assert inst.warning_message and "komut kanalı" in inst.warning_message


def test_successful_acquire_has_no_warning(qtbot):
    from dikte.platform.single_instance import IpcStatus

    inst = SingleInstance(f"dikte-test-{uuid.uuid4().hex[:8]}")
    assert inst.try_acquire() is True
    assert inst.status is IpcStatus.LISTENING
    assert inst.warning_message is None


def test_second_instance_status_already_running(qtbot):
    from dikte.platform.single_instance import IpcStatus

    name = f"dikte-test-{uuid.uuid4().hex[:8]}"
    first = SingleInstance(name)
    assert first.try_acquire() is True
    second = SingleInstance(name)
    assert second.try_acquire() is False
    assert second.status is IpcStatus.ALREADY_RUNNING


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
