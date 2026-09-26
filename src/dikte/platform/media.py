"""Kayıt sırasında çalan medyayı duraklatır, kayıttan sonra yalnızca onları sürdürür.

Asla körlemesine oynat/duraklat (toggle) gönderilmez: o, hiçbir şey çalmıyorken oynatmayı
BAŞLATIRDI. Yalnızca o an "çalıyor" durumundaki oturumlar duraklatılır ve hatırlanır;
sürdürmede yalnızca hâlâ "duraklatılmış" olanlara oynat komutu gider.

- Linux: `playerctl` (MPRIS). Kurulu değilse bir kez bilgi günlüğü, sonra işlem yok.
- Windows: WinRT GlobalSystemMediaTransportControlsSessionManager, isteğe bağlı `winsdk`
  paketiyle (`pip install "dikte[media]"`). Yoksa bir kez bilgi günlüğü, işlem yok.

Tüm çağrılar kısa zaman aşımlıdır; yine de GUI iş parçacığını hiç bekletmemek için
çağıran taraf `pause()`/`resume()`'u bir işçi iş parçacığında çalıştırabilir.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import sys
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

log = logging.getLogger(__name__)

_PLAYERCTL_TIMEOUT_S = 1.0
_WINSDK_TIMEOUT_S = 1.5
# GlobalSystemMediaTransportControlsSessionPlaybackStatus değerleri.
_WIN_PLAYING = 4
_WIN_PAUSED = 5

Runner = Callable[[list[str], float], Any]


class MediaBackend(Protocol):
    """Platforma özgü medya denetimi; belirteçler arka uca özgüdür (oynatıcı adı/oturum)."""

    def pause_playing(self) -> tuple[object, ...]:
        """Çalan oturumları duraklatır; duraklattıklarının belirteçlerini döndürür."""
        ...

    def resume(self, tokens: Sequence[object]) -> None:
        """Yalnızca verilen ve hâlâ duraklatılmış oturumları sürdürür."""
        ...


def _default_runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


class PlayerctlBackend:
    """Linux: MPRIS oynatıcılarını `playerctl` ile tek tek yoklar; belirteç oynatıcı adıdır."""

    def __init__(
        self,
        *,
        runner: Runner = _default_runner,
        which: Callable[[str], str | None] = shutil.which,
        timeout_s: float = _PLAYERCTL_TIMEOUT_S,
    ):
        self._runner = runner
        self._which = which
        self._timeout_s = timeout_s
        self._warned = False

    def _binary(self) -> str | None:
        path = self._which("playerctl")
        if path is None and not self._warned:
            log.info("medya duraklatma için playerctl gerekli; kurulu değil, atlanıyor")
            self._warned = True
        return path

    def _run(self, binary: str, *args: str) -> tuple[int, str]:
        result = self._runner([binary, *args], self._timeout_s)
        return int(result.returncode), str(getattr(result, "stdout", "") or "")

    def _status(self, binary: str, player: str) -> str:
        code, out = self._run(binary, "-p", player, "status")
        return out.strip() if code == 0 else ""

    def pause_playing(self) -> tuple[object, ...]:
        binary = self._binary()
        if binary is None:
            return ()
        code, out = self._run(binary, "-l")
        if code != 0:  # "No players found"
            return ()
        paused: list[object] = []
        for player in (line.strip() for line in out.splitlines()):
            if (
                player
                and self._status(binary, player) == "Playing"
                and self._run(binary, "-p", player, "pause")[0] == 0
            ):
                paused.append(player)
        return tuple(paused)

    def resume(self, tokens: Sequence[object]) -> None:
        binary = self._binary()
        if binary is None:
            return
        for player in tokens:
            if self._status(binary, str(player)) == "Paused":
                self._run(binary, "-p", str(player), "play")


class WinsdkBackend:
    """Windows: WinRT medya oturumlarını denetler; belirteç oturum nesnesinin kendisidir.

    Her çağrı kendi `asyncio.run` döngüsünde, `timeout_s` ile sınırlı çalışır."""

    def __init__(
        self,
        *,
        manager_factory: Callable[[], Awaitable[Any]],
        timeout_s: float = _WINSDK_TIMEOUT_S,
    ):
        self._manager_factory = manager_factory
        self._timeout_s = timeout_s

    def _run(self, coro: Awaitable[Any]) -> Any:
        async def bounded() -> Any:
            return await asyncio.wait_for(coro, self._timeout_s)

        return asyncio.run(bounded())

    @staticmethod
    def _status(session: Any) -> int | None:
        info = session.get_playback_info()
        return None if info is None else int(info.playback_status)

    async def _pause_async(self) -> tuple[object, ...]:
        manager = await self._manager_factory()
        paused: list[object] = []
        for session in manager.get_sessions():
            if self._status(session) == _WIN_PLAYING and await session.try_pause_async():
                paused.append(session)
        return tuple(paused)

    async def _resume_async(self, sessions: Sequence[Any]) -> None:
        for session in sessions:
            if self._status(session) == _WIN_PAUSED:
                await session.try_play_async()

    def pause_playing(self) -> tuple[object, ...]:
        return self._run(self._pause_async())

    def resume(self, tokens: Sequence[object]) -> None:
        self._run(self._resume_async(tokens))


def _load_winsdk_manager() -> Callable[[], Awaitable[Any]] | None:
    try:
        from winsdk.windows.media.control import (  # type: ignore[import-not-found]
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )
    except ImportError:
        return None

    async def factory() -> Any:
        return await Manager.request_async()

    return factory


def _default_backend(
    platform: str, winsdk_loader: Callable[[], Callable[[], Awaitable[Any]] | None]
) -> MediaBackend | None:
    if platform == "win32":
        factory = winsdk_loader()
        if factory is None:
            log.info(
                "medya duraklatma için winsdk paketi kurulu değil "
                '(pip install "dikte[media]"); atlanıyor'
            )
            return None
        return WinsdkBackend(manager_factory=factory)
    if platform.startswith(("linux", "freebsd")):
        return PlayerctlBackend()
    log.info("medya duraklatma bu platformda desteklenmiyor: %s", platform)
    return None


class MediaPauser:
    """Kayıt başlarken `pause()`, bitince `resume()`. Hatalar günlüğe yazılır, yükseltilmez:
    medya duraklatma bir kolaylıktır, dikteyi asla engellememeli."""

    _UNSET: Any = object()

    def __init__(
        self,
        backend: MediaBackend | None = _UNSET,
        *,
        platform: str = sys.platform,
        winsdk_loader: Callable[[], Callable[[], Awaitable[Any]] | None] = _load_winsdk_manager,
    ):
        if backend is MediaPauser._UNSET:
            backend = _default_backend(platform, winsdk_loader)
        self._backend: MediaBackend | None = backend
        self._paused: tuple[object, ...] = ()

    @property
    def backend(self) -> MediaBackend | None:
        return self._backend

    def pause(self) -> None:
        """Çalanları duraklatıp hatırlar; önceki duraklatma henüz sürdürülmediyse bir şey yapmaz."""
        if self._backend is None or self._paused:
            return
        try:
            self._paused = tuple(self._backend.pause_playing())
        except Exception:
            log.exception("medya duraklatılamadı; kayıt medya çalarken sürüyor")
            self._paused = ()

    def resume(self) -> None:
        """Yalnızca `pause()`un duraklattıklarını sürdürür ve listeyi sıfırlar."""
        tokens, self._paused = self._paused, ()
        if self._backend is None or not tokens:
            return
        try:
            self._backend.resume(tokens)
        except Exception:
            log.exception("duraklatılan medya sürdürülemedi; oynatıcıdan elle devam ettirin")
