import asyncio
import subprocess
from types import SimpleNamespace

from dikte.platform.media import MediaPauser, PlayerctlBackend, WinrtBackend


class FakePlayerctl:
    def __init__(self, players):
        self.players = dict(players)  # ad → "Playing" | "Paused" | "Stopped"
        self.calls = []

    def __call__(self, args, timeout):
        self.calls.append(args)
        assert timeout <= 2
        assert args[0] == "/usr/bin/playerctl"
        rest = args[1:]
        if rest == ["-l"]:
            if not self.players:
                return SimpleNamespace(returncode=1, stdout="", stderr="No players found")
            return SimpleNamespace(returncode=0, stdout="\n".join(self.players) + "\n")
        assert rest[0] == "-p"
        name, cmd = rest[1], rest[2]
        if cmd == "status":
            return SimpleNamespace(returncode=0, stdout=self.players[name] + "\n")
        if cmd == "pause":
            self.players[name] = "Paused"
        elif cmd == "play":
            self.players[name] = "Playing"
        return SimpleNamespace(returncode=0, stdout="")


def _linux(fake):
    backend = PlayerctlBackend(runner=fake, which=lambda n: "/usr/bin/playerctl")
    return MediaPauser(backend=backend)


def test_pauses_only_playing_players_and_resumes_them():
    fake = FakePlayerctl({"spotify": "Playing", "vlc": "Paused", "mpv": "Stopped"})
    pauser = _linux(fake)
    pauser.pause()
    assert fake.players == {"spotify": "Paused", "vlc": "Paused", "mpv": "Stopped"}
    pauser.resume()
    assert fake.players == {"spotify": "Playing", "vlc": "Paused", "mpv": "Stopped"}


def test_resume_without_pause_never_starts_playback():
    fake = FakePlayerctl({"vlc": "Paused"})
    pauser = _linux(fake)
    pauser.resume()
    assert fake.players == {"vlc": "Paused"}
    assert not any("play" in c for c in fake.calls)


def test_resume_is_one_shot():
    fake = FakePlayerctl({"spotify": "Playing"})
    pauser = _linux(fake)
    pauser.pause()
    pauser.resume()
    fake.players["spotify"] = "Paused"  # kullanıcı sonradan kendisi durdurdu
    pauser.resume()
    assert fake.players["spotify"] == "Paused"


def test_resume_skips_player_user_already_restarted_or_stopped():
    fake = FakePlayerctl({"spotify": "Playing"})
    pauser = _linux(fake)
    pauser.pause()
    fake.players["spotify"] = "Stopped"
    pauser.resume()
    assert fake.players["spotify"] == "Stopped"


def test_no_players_is_noop():
    fake = FakePlayerctl({})
    pauser = _linux(fake)
    pauser.pause()
    pauser.resume()


def test_missing_playerctl_logs_once_and_noops(caplog):
    caplog.set_level("INFO")
    calls = []
    backend = PlayerctlBackend(runner=lambda a, t: calls.append(a), which=lambda n: None)
    pauser = MediaPauser(backend=backend)
    pauser.pause()
    pauser.pause()
    pauser.resume()
    assert calls == []
    assert caplog.text.count("playerctl") == 1


def test_playerctl_timeout_is_logged_not_raised(caplog):
    def slow(args, timeout):
        raise subprocess.TimeoutExpired(args, timeout)

    backend = PlayerctlBackend(runner=slow, which=lambda n: "/usr/bin/playerctl")
    MediaPauser(backend=backend).pause()
    assert "medya" in caplog.text.lower()


def test_no_backend_is_noop():
    pauser = MediaPauser(backend=None)
    pauser.pause()
    pauser.resume()


def test_default_backend_on_linux_is_playerctl():
    pauser = MediaPauser(platform="linux")
    assert isinstance(pauser.backend, PlayerctlBackend)


def test_windows_without_winrt_logs_info_and_noops(caplog):
    caplog.set_level("INFO")
    pauser = MediaPauser(platform="win32", winrt_loader=lambda: None)
    assert pauser.backend is None
    pauser.pause()
    assert "winrt" in caplog.text
    assert "winsdk" not in caplog.text


# --- Windows (WinRT) arka ucu -------------------------------------------------

PLAYING, PAUSED, STOPPED = 4, 5, 3


class FakeSession:
    def __init__(self, status):
        self.status = status

    def get_playback_info(self):
        return SimpleNamespace(playback_status=self.status)

    async def try_pause_async(self):
        self.status = PAUSED
        return True

    async def try_play_async(self):
        self.status = PLAYING
        return True


class FakeManager:
    def __init__(self, sessions):
        self.sessions = sessions

    def get_sessions(self):
        return self.sessions


def _win(sessions):
    async def factory():
        return FakeManager(sessions)

    return MediaPauser(backend=WinrtBackend(manager_factory=factory))


def test_winrt_pauses_only_playing_sessions_and_resumes_them():
    playing, paused, stopped = FakeSession(PLAYING), FakeSession(PAUSED), FakeSession(STOPPED)
    pauser = _win([playing, paused, stopped])
    pauser.pause()
    assert (playing.status, paused.status, stopped.status) == (PAUSED, PAUSED, STOPPED)
    pauser.resume()
    assert (playing.status, paused.status, stopped.status) == (PLAYING, PAUSED, STOPPED)


def test_winrt_timeout_is_logged_not_raised(caplog):
    async def hang():
        await asyncio.sleep(10)

    pauser = MediaPauser(backend=WinrtBackend(manager_factory=hang, timeout_s=0.05))
    pauser.pause()
    pauser.resume()
    assert "medya" in caplog.text.lower()


def test_playerctl_timeout_on_one_player_keeps_already_paused_ones():
    """N. oynatıcıda zaman aşımı, önceden duraklatılanları kaybettirmemeli: aksi hâlde
    kayıttan sonra hiçbiri sürdürülmezdi."""
    fake = FakePlayerctl({"spotify": "Playing", "takilan": "Playing", "vlc": "Playing"})

    def runner(args, timeout):
        if args[1:3] == ["-p", "takilan"]:
            raise subprocess.TimeoutExpired(args, timeout)
        return fake(args, timeout)

    backend = PlayerctlBackend(runner=runner, which=lambda n: "/usr/bin/playerctl")
    pauser = MediaPauser(backend=backend)
    pauser.pause()
    assert fake.players["spotify"] == "Paused" and fake.players["vlc"] == "Paused"
    pauser.resume()
    assert fake.players["spotify"] == "Playing" and fake.players["vlc"] == "Playing"


def test_playerctl_resume_continues_after_one_player_fails(caplog):
    fake = FakePlayerctl({"a": "Playing", "b": "Playing"})
    backend = PlayerctlBackend(runner=fake, which=lambda n: "/usr/bin/playerctl")
    assert backend.pause_playing() == ("a", "b")

    def runner(args, timeout):
        if args[1:3] == ["-p", "a"]:
            raise OSError("playerctl çöktü")
        return fake(args, timeout)

    backend = PlayerctlBackend(runner=runner, which=lambda n: "/usr/bin/playerctl")
    backend.resume(("a", "b"))
    assert fake.players["b"] == "Playing"
    assert "oynatıcı" in caplog.text


class HangingSession(FakeSession):
    async def try_pause_async(self):
        await asyncio.sleep(10)
        return True


class BrokenSession(FakeSession):
    def get_playback_info(self):
        raise OSError("oturum kapandı")


def test_winrt_timeout_keeps_sessions_paused_before_it():
    first, hanging = FakeSession(PLAYING), HangingSession(PLAYING)

    async def factory():
        return FakeManager([first, hanging])

    backend = WinrtBackend(manager_factory=factory, timeout_s=0.1)
    assert backend.pause_playing() == (first,)
    backend.resume((first,))
    assert first.status == PLAYING


def test_winrt_skips_failing_session_and_pauses_the_rest(caplog):
    broken, playing = BrokenSession(PLAYING), FakeSession(PLAYING)

    async def factory():
        return FakeManager([broken, playing])

    backend = WinrtBackend(manager_factory=factory)
    assert backend.pause_playing() == (playing,)
    assert "oturum" in caplog.text.lower()


def test_winrt_status_accepts_pywinrt_int_enum():
    """pywinrt 3.x durumları `enum.IntEnum` olarak verir (PLAYING=4, PAUSED=5)."""
    import enum

    class Status(enum.IntEnum):
        PLAYING = 4
        PAUSED = 5

    session = FakeSession(Status.PLAYING)

    async def factory():
        return FakeManager([session])

    assert WinrtBackend(manager_factory=factory).pause_playing() == (session,)


def test_load_winrt_manager_imports_pywinrt_modules():
    from dikte.platform.media import _load_winrt_manager

    imported = []

    class Manager:
        @staticmethod
        async def request_async():
            return "yönetici"

    def importer(name):
        imported.append(name)
        return SimpleNamespace(GlobalSystemMediaTransportControlsSessionManager=Manager)

    factory = _load_winrt_manager(import_module=importer)
    assert factory is not None

    async def build():
        return await factory()

    assert asyncio.run(build()) == "yönetici"
    assert "winrt.windows.media.control" in imported
    # IAsyncOperation'ı beklemek ve oturum listesini (IVectorView) gezmek bu
    # projeksiyon paketlerini gerektirir; eksikse özellik baştan devre dışı kalmalı.
    assert "winrt.windows.foundation" in imported
    assert "winrt.windows.foundation.collections" in imported
    assert not any(name.startswith("winsdk") for name in imported)


def test_load_winrt_manager_returns_none_when_a_package_is_missing():
    from dikte.platform.media import _load_winrt_manager

    def importer(name):
        if name == "winrt.windows.foundation.collections":
            raise ModuleNotFoundError(name)
        return SimpleNamespace(GlobalSystemMediaTransportControlsSessionManager=object)

    assert _load_winrt_manager(import_module=importer) is None


def test_media_extra_uses_pywinrt_for_all_python_versions():
    import tomllib
    from pathlib import Path

    data = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text("utf-8"))
    media = data["project"]["optional-dependencies"]["media"]
    names = {req.split(">=")[0] for req in media}
    assert names >= {
        "winrt-runtime",
        "winrt-Windows.Media.Control",
        "winrt-Windows.Foundation",
        "winrt-Windows.Foundation.Collections",
    }
    assert all("sys_platform == 'win32'" in req for req in media)
    assert not any("winsdk" in req or "python_version" in req for req in media)


def test_pyinstaller_spec_collects_winrt_not_winsdk():
    from pathlib import Path

    spec = (Path(__file__).parents[1] / "packaging" / "dikte.spec").read_text("utf-8")
    assert "winsdk" not in spec
    assert 'collect_submodules("winrt")' in spec
