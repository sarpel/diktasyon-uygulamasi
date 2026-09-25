import asyncio
import subprocess
from types import SimpleNamespace

from dikte.platform.media import MediaPauser, PlayerctlBackend, WinsdkBackend


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


def test_windows_without_winsdk_logs_info_and_noops(caplog):
    caplog.set_level("INFO")
    pauser = MediaPauser(platform="win32", winsdk_loader=lambda: None)
    assert pauser.backend is None
    pauser.pause()
    assert "winsdk" in caplog.text


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

    return MediaPauser(backend=WinsdkBackend(manager_factory=factory))


def test_winsdk_pauses_only_playing_sessions_and_resumes_them():
    playing, paused, stopped = FakeSession(PLAYING), FakeSession(PAUSED), FakeSession(STOPPED)
    pauser = _win([playing, paused, stopped])
    pauser.pause()
    assert (playing.status, paused.status, stopped.status) == (PAUSED, PAUSED, STOPPED)
    pauser.resume()
    assert (playing.status, paused.status, stopped.status) == (PLAYING, PAUSED, STOPPED)


def test_winsdk_timeout_is_logged_not_raised(caplog):
    async def hang():
        await asyncio.sleep(10)

    pauser = MediaPauser(backend=WinsdkBackend(manager_factory=hang, timeout_s=0.05))
    pauser.pause()
    pauser.resume()
    assert "medya" in caplog.text.lower()
