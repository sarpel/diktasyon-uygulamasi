"""Başarısız diktelerin sesini saklamak/yeniden okumak için 16 kHz mono int16 WAV (stdlib)."""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000


def save_wav(path: Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    """float32 [-1, 1] sesi int16 PCM olarak yazar (dizin yoksa oluşturulur, üzerine yazar)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0) * 32767).astype(
        "<i2"
    )
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    if sys.platform != "win32":
        tmp.chmod(0o600)  # dikte edilen konuşmanın kendisi; başka kullanıcılar okumasın
    tmp.replace(path)


def load_wav(path: Path) -> np.ndarray:
    """`save_wav` ile yazılmış dosyayı float32 mono diziye çevirir."""
    with wave.open(str(path), "rb") as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        if rate != SAMPLE_RATE or channels != 1 or width != 2:
            raise ValueError(
                f"Beklenmeyen WAV biçimi ({rate} Hz, {channels} kanal, {8 * width} bit); "
                f"{SAMPLE_RATE} Hz mono 16 bit bekleniyordu."
            )
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32767.0
