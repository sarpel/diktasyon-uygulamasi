from __future__ import annotations

import logging
import threading
from typing import Callable, Protocol

import numpy as np

from dikte import paths
from dikte.config import SttSettings
from dikte.stt.result import Segment, TranscriptResult

log = logging.getLogger(__name__)


class SttError(Exception):
    pass


class SttEngine(Protocol):
    @property
    def is_loaded(self) -> bool: ...

    def load(self) -> None: ...

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> TranscriptResult: ...


def _default_model_factory(*args, **kwargs):
    from dikte.cuda_dlls import register_nvidia_dll_dirs

    register_nvidia_dll_dirs()
    from faster_whisper import WhisperModel

    return WhisperModel(*args, **kwargs)


class FasterWhisperEngine:
    def __init__(self, settings: SttSettings, model_factory: Callable | None = None):
        self._settings = settings
        self._factory = model_factory or _default_model_factory
        self._model = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            try:
                self._model = self._factory(
                    self._settings.model,
                    device=self._settings.device,
                    compute_type=self._settings.compute_type,
                    download_root=str(paths.models_dir()),
                )
            except Exception as exc:
                raise SttError(f"STT modeli yüklenemedi: {exc}") from exc
        log.info(
            "STT modeli yüklendi: %s (%s/%s)",
            self._settings.model,
            self._settings.device,
            self._settings.compute_type,
        )

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> TranscriptResult:
        if audio.size == 0:
            raise SttError("Ses kaydı boş")
        if not self.is_loaded:
            self.load()
        lang = language or self._settings.language
        try:
            with self._lock:
                seg_iter, info = self._model.transcribe(
                    audio.astype(np.float32, copy=False),
                    language=lang,
                    task="transcribe",
                    beam_size=self._settings.beam_size,
                    vad_filter=self._settings.vad_filter,
                    initial_prompt=self._settings.initial_prompt or None,
                    condition_on_previous_text=True,
                )
                segments = tuple(Segment(s.start, s.end, s.text.strip()) for s in seg_iter)
        except Exception as exc:
            raise SttError(f"Transkripsiyon hatası: {exc}") from exc
        text = " ".join(s.text for s in segments if s.text).strip()
        return TranscriptResult(
            text=text,
            language=info.language,
            duration_s=float(info.duration),
            segments=segments,
        )
