"""Kayıt başlat/durdur ve hata için bellekte üretilen kısa uyarı sesleri."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal

import numpy as np

from dikte.core.state import DictationState

log = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_AMPLITUDE = 0.2
_FADE_MS = 5

SoundKind = Literal["start", "stop", "error"]


def tone(freq_hz: float, ms: int, sr: int = _SAMPLE_RATE) -> np.ndarray:
    """Verilen frekans ve sürede, kenarları yumuşatılmış (fade-in/out) bir sinüs tonu üretir."""
    n = int(sr * ms / 1000)
    t = np.arange(n, dtype=np.float32) / sr
    wave = np.sin(2 * np.pi * freq_hz * t).astype(np.float32)

    fade_n = min(int(sr * _FADE_MS / 1000), n // 2)
    envelope = np.ones(n, dtype=np.float32)
    if fade_n > 0:
        ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
        envelope[:fade_n] = ramp
        envelope[n - fade_n :] = ramp[::-1]

    return (wave * envelope * _AMPLITUDE).astype(np.float32)


def _error_tone(sr: int = _SAMPLE_RATE) -> np.ndarray:
    beep = tone(330.0, 120, sr)
    gap = np.zeros(int(sr * 60 / 1000), dtype=np.float32)
    return np.concatenate([beep, gap, beep]).astype(np.float32)


def _default_player(data: np.ndarray, sr: int) -> None:
    import sounddevice as sd

    sd.play(data, sr)


class SoundPlayer:
    """Kayıt durum geçişlerinde ve hatalarda kısa uyarı tonları çalar.

    `player` enjekte edilebilir: testlerde gerçek ses donanımı gerekmez.
    """

    def __init__(
        self,
        enabled: bool = True,
        player: Callable[[np.ndarray, int], None] | None = None,
    ) -> None:
        self._enabled = enabled
        self._player = player or _default_player
        self._warned = False
        self._tones: dict[SoundKind, np.ndarray] = {
            "start": tone(880.0, 90),
            "stop": tone(660.0, 90),
            "error": _error_tone(),
        }

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def play(self, kind: SoundKind) -> None:
        """Kapalıysa bir şey yapmaz; ses cihazı hatası yükseltilmez, yalnızca bir kez loglanır."""
        if not self._enabled:
            return
        try:
            self._player(self._tones[kind], _SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001 - ses cihazı hatası dikteyi durdurmamalı
            if not self._warned:
                self._warned = True
                log.warning("ses çalınamadı: %s", exc)

    def on_state(self, state: DictationState) -> None:
        """RECORDING'e girişte "start", TRANSCRIBING'e girişte "stop" tonu çalar."""
        if state is DictationState.RECORDING:
            self.play("start")
        elif state is DictationState.TRANSCRIBING:
            self.play("stop")

    def on_error(self, _msg: str) -> None:
        self.play("error")
