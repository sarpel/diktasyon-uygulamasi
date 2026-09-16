from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import numpy as np
from PySide6.QtCore import QObject, Signal

from dikte.audio.levels import bucketize, rms
from dikte.config import AudioSettings

log = logging.getLogger(__name__)
BLOCK_SIZE = 1600  # 100 ms @ 16 kHz
BUCKETS = 32


def _default_stream_factory(**kwargs):
    import sounddevice as sd  # type: ignore[import-not-found]

    return sd.InputStream(**kwargs)


class AudioRecorder(QObject):
    level_changed = Signal(float)
    buckets_changed = Signal(object)
    limit_reached = Signal()
    silence_reached = Signal()
    chunk_ready = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        settings: AudioSettings,
        stream_factory: Callable | None = None,
        parent=None,
        *,
        chunk_s: float = 0.0,
        max_chunk_s: float = 45.0,
    ):
        super().__init__(parent)
        self._settings = settings
        self._factory = stream_factory or _default_stream_factory
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._total = 0
        self._chunk_samples = 0
        self._chunk_s = chunk_s
        self._max_chunk_s = max_chunk_s
        self._limit_hit = False
        self._speech_seen = False
        self._silent_samples = 0
        self._silence_hit = False
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def update_settings(self, settings: AudioSettings) -> None:
        """Süren kayıt etkilenmez; yeni cihaz/parametreler bir sonraki `start()`'ta geçerli olur."""
        self._settings = settings

    def set_chunking(self, chunk_s: float, max_chunk_s: float) -> None:
        """Canlı parça parça çözümleme parametrelerini günceller (`chunk_s=0` kapatır)."""
        self._chunk_s = chunk_s
        self._max_chunk_s = max_chunk_s

    def start(self) -> None:
        if self._stream is not None:
            return
        self._chunks, self._total, self._limit_hit = [], 0, False
        self._chunk_samples = 0
        self._speech_seen, self._silent_samples, self._silence_hit = False, 0, False
        try:
            stream = self._factory(
                callback=self._on_audio,
                samplerate=self._settings.sample_rate,
                channels=1,
                dtype="float32",
                device=self._settings.device_index,
                blocksize=BLOCK_SIZE,
            )
            stream.start()
            self._stream = stream
        except Exception as exc:  # sounddevice.PortAudioError vb.
            self._stream = None
            log.exception("mikrofon açılamadı")
            self.error.emit(f"Mikrofon açılamadı: {exc}")

    def stop(self) -> np.ndarray:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                log.exception("stream kapatılırken hata")
        with self._lock:
            chunks, self._chunks = self._chunks, []
            self._total = 0
            self._chunk_samples = 0
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:
            log.warning("audio status: %s", status)
        # PortAudio giriş tamponunu her geri çağırmada yeniden kullanır; view saklamak
        # sonradan üzerine yazılan (bozuk/çöp) ses verisi demektir. Bu yüzden kopya alınır.
        frame: np.ndarray | None = np.array(indata, dtype=np.float32).reshape(-1)
        limit = self._settings.max_seconds * self._settings.sample_rate  # 0 = sınırsız
        first_hit = False
        level = 0.0
        chunk_to_emit: np.ndarray | None = None
        with self._lock:
            if limit > 0:
                room = limit - self._total
                if room <= 0:
                    first_hit, self._limit_hit = not self._limit_hit, True
                    frame = None
                else:
                    frame = frame[:room]
            if frame is not None:
                self._chunks.append(frame)
                self._total += frame.shape[0]
                self._chunk_samples += frame.shape[0]
                # Sınırı tam dolduran blok da kaydı hemen bitirir (bir blok gecikmeden).
                if 0 < limit <= self._total and not self._limit_hit:
                    first_hit, self._limit_hit = True, True
                level = rms(frame)
                if self._chunk_s > 0:
                    chunk_to_emit = self._maybe_flush_chunk(level)
        if first_hit:
            self.limit_reached.emit()
        if frame is None:
            return
        self._track_silence(level, frame.shape[0])
        self.level_changed.emit(level)
        self.buckets_changed.emit(bucketize(frame, BUCKETS))
        if chunk_to_emit is not None:
            self.chunk_ready.emit(chunk_to_emit)

    def _maybe_flush_chunk(self, level: float) -> np.ndarray | None:
        """Kilit altında çağrılır. Toplanan süre `chunk_s`i geçip blok sessizse, ya da
        `max_chunk_s`e ulaşılmışsa (sessizlikten bağımsız sert kesim) parçayı boşaltır."""
        duration_s = self._chunk_samples / self._settings.sample_rate
        should_flush = duration_s >= self._max_chunk_s or (
            duration_s >= self._chunk_s and level < self._settings.silence_threshold
        )
        if not should_flush or not self._chunks:
            return None
        chunk, self._chunks = self._chunks, []
        self._chunk_samples = 0
        return np.concatenate(chunk).astype(np.float32, copy=False)

    def _track_silence(self, level: float, n: int) -> None:
        stop_s, thr = self._settings.silence_stop_s, self._settings.silence_threshold
        if stop_s <= 0 or self._silence_hit:
            return
        if level > thr * 3:
            self._speech_seen, self._silent_samples = True, 0
            return
        if not self._speech_seen:
            return
        self._silent_samples += n
        if self._silent_samples >= stop_s * self._settings.sample_rate:
            self._silence_hit = True
            self.silence_reached.emit()
