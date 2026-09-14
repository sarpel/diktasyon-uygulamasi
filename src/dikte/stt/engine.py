from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Protocol

import numpy as np

from dikte import paths
from dikte.config import SttSettings
from dikte.stt.result import Segment, TranscriptResult

log = logging.getLogger(__name__)
SAMPLE_RATE = 16000  # Whisper her zaman 16 kHz bekler
# GPU desteklemiyorsa bu sırayla ilk desteklenen tipe düşülür.
# float16 CC >= 7.0, int8 CC >= 7.0 veya 6.1 ister; eski kartlarda float32 kalır.
COMPUTE_TYPE_PREFERENCE = ("float16", "int8_float16", "bfloat16", "int8_float32", "float32")


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


def _default_pipeline_factory(model):
    from faster_whisper import BatchedInferencePipeline

    return BatchedInferencePipeline(model=model)


def _default_supported_types_probe() -> set[str]:
    import ctranslate2

    return set(ctranslate2.get_supported_compute_types("cuda"))


def _default_cuda_probe() -> int:
    """Kullanılabilir CUDA aygıtı sayısı; sorgulanamazsa 0."""
    from dikte.cuda_dlls import register_nvidia_dll_dirs

    register_nvidia_dll_dirs()
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except (ImportError, RuntimeError, OSError) as exc:  # sürücü/kütüphane eksik
        log.error("CUDA aygıtları sorgulanamadı: %s", exc)
        return 0


class FasterWhisperEngine:
    def __init__(
        self,
        settings: SttSettings,
        model_factory: Callable | None = None,
        pipeline_factory: Callable | None = None,
        cuda_probe: Callable[[], int] | None = None,
        supported_types_probe: Callable[[], set[str]] | None = None,
    ):
        self._settings = settings
        self._factory = model_factory or _default_model_factory
        self._pipeline_factory = pipeline_factory or _default_pipeline_factory
        self._cuda_probe = cuda_probe or _default_cuda_probe
        self._types_probe = supported_types_probe or _default_supported_types_probe
        self._model = None
        self._pipeline = None
        self._compute_type = settings.compute_type
        self._downgraded = False
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def is_downgraded(self) -> bool:
        """Ayardaki compute_type GPU'da desteklenmediği için düşürüldü mü?"""
        return self._downgraded

    @property
    def compute_type(self) -> str:
        """Fiilen kullanılan compute_type (GPU desteğine göre düşürülmüş olabilir)."""
        return self._compute_type

    def _resolve_compute_type(self) -> str:
        """Ayardaki tip GPU'da yoksa desteklenen en iyi tipe düşer."""
        wanted = self._settings.compute_type
        try:
            supported = self._types_probe()
        except Exception as exc:  # noqa: BLE001 - sorgu başarısızsa CT2 kendi hatasını versin
            log.warning("desteklenen compute_type listesi alınamadı: %s", exc)
            return wanted
        if wanted in supported:
            return wanted
        for candidate in COMPUTE_TYPE_PREFERENCE:
            if candidate in supported:
                log.warning(
                    "GPU '%s' compute_type'ını desteklemiyor; '%s' kullanılıyor",
                    wanted,
                    candidate,
                )
                self._downgraded = True
                return candidate
        raise SttError(
            f"GPU hiçbir compute_type'ı desteklemiyor (istenen: {wanted}). "
            "NVIDIA sürücüsünü ve CUDA kurulumunu kontrol edin."
        )

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            if self._cuda_probe() < 1:
                raise SttError(
                    "CUDA destekli GPU bulunamadı. Dikte yalnızca GPU üzerinde çalışır; "
                    "NVIDIA sürücüsünü (CUDA 12 uyumlu, ≥ 525) ve cuBLAS/cuDNN paketlerini "
                    'kontrol edin (uv pip install -e ".[cuda]").'
                )
            compute_type = self._compute_type = self._resolve_compute_type()
            try:
                self._model = self._factory(
                    self._settings.model,
                    device=self._settings.device,
                    compute_type=compute_type,
                    download_root=str(paths.models_dir()),
                )
            except Exception as exc:
                raise SttError(f"STT modeli yüklenemedi: {exc}") from exc
        log.info(
            "STT modeli yüklendi: %s (%s/%s)",
            self._settings.model,
            self._settings.device,
            self._compute_type,
        )

    def _use_batching(self, audio: np.ndarray) -> bool:
        if not self._settings.batch_enabled:
            return False
        return audio.size / SAMPLE_RATE >= self._settings.batch_threshold_s

    def _get_pipeline(self):
        if self._pipeline is None:
            self._pipeline = self._pipeline_factory(self._model)
            log.info("Toplu çözümleme açıldı (batch_size=%s)", self._settings.batch_size)
        return self._pipeline

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> TranscriptResult:
        if audio.size == 0:
            raise SttError("Ses kaydı boş")
        if not self.is_loaded:
            self.load()
        lang = language or self._settings.language
        kwargs = {
            "language": lang,
            "task": "transcribe",
            "beam_size": self._settings.beam_size,
            "vad_filter": self._settings.vad_filter,
            "initial_prompt": self._settings.initial_prompt or None,
        }
        try:
            with self._lock:
                if self._use_batching(audio):
                    target = self._get_pipeline()
                    kwargs["batch_size"] = self._settings.batch_size
                else:
                    target = self._model
                    kwargs["condition_on_previous_text"] = True
                seg_iter, info = target.transcribe(audio.astype(np.float32, copy=False), **kwargs)
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
