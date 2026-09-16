from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Protocol

import numpy as np

from dikte import paths
from dikte.config import SttSettings
from dikte.stt.hallucinations import filter_segments
from dikte.stt.result import Segment, TranscriptResult

log = logging.getLogger(__name__)
SAMPLE_RATE = 16000  # Whisper her zaman 16 kHz bekler
WARM_UP_SECONDS = 1.0
# GPU desteklemiyorsa bu sırayla ilk desteklenen tipe düşülür.
# float16 CC >= 7.0, int8 CC >= 7.0 veya 6.1 ister; eski kartlarda float32 kalır.
COMPUTE_TYPE_PREFERENCE = ("float16", "int8_float16", "bfloat16", "int8_float32", "float32")


class SttError(Exception):
    pass


class SttEngine(Protocol):
    @property
    def is_loaded(self) -> bool: ...

    @property
    def active_model(self) -> str: ...

    def load(self) -> None: ...

    def warm_up(self) -> None: ...

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> TranscriptResult: ...


def _default_model_factory(*args, **kwargs):
    from dikte.cuda_dlls import register_nvidia_dll_dirs

    register_nvidia_dll_dirs()
    from faster_whisper import WhisperModel

    return WhisperModel(*args, **kwargs)


def _vad_options(settings: SttSettings) -> dict:
    return {
        "threshold": settings.vad_threshold,
        "min_silence_duration_ms": settings.vad_min_silence_ms,
        "speech_pad_ms": settings.vad_speech_pad_ms,
    }


def _default_speech_probe(audio: np.ndarray, settings: SttSettings) -> list[dict] | bool:
    """Kayıttaki konuşma aralıkları (örnek cinsinden). Silero VAD (faster-whisper içinde gömülü) ile bulunur.

    Toplu boru hattının kendi kullandığı max_speech_duration_s=30 ile hesaplanır, böylece
    aynı zaman damgaları hem "hiç konuşma var mı" ön kontrolünde hem de toplu çözümlemede
    (VAD'i ikinci kez çalıştırmadan) kullanılabilir.
    """
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    options = VadOptions(**_vad_options(settings), max_speech_duration_s=30)
    return get_speech_timestamps(audio.astype(np.float32, copy=False), options)


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
        speech_probe: Callable[[np.ndarray, SttSettings], list[dict] | bool] | None = None,
    ):
        self._settings = settings
        self._factory = model_factory or _default_model_factory
        self._pipeline_factory = pipeline_factory or _default_pipeline_factory
        self._cuda_probe = cuda_probe or _default_cuda_probe
        self._types_probe = supported_types_probe or _default_supported_types_probe
        self._speech_probe = speech_probe or _default_speech_probe
        self._model = None
        self._pipeline = None
        self._compute_type = settings.compute_type
        self._downgraded = False
        self._lock = threading.Lock()
        self._hotwords = ""
        self._prompt_terms = ""

    def set_dictionary(self, hotwords: str, prompt_terms: str) -> None:
        self._hotwords, self._prompt_terms = hotwords, prompt_terms

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def active_model(self) -> str:
        """Motorun kurulduğu andaki model adı (ayar sonrası restart'a kadar gerçektir)."""
        return self._settings.model

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

    def update_settings(self, settings: SttSettings) -> bool:
        """Ayarları uygular; model/hassasiyet/cihaz değiştiyse modeli arka planda düşürür.

        Dönen bool, arayana modelin yeniden yüklenmesi (bir sonraki `load()`/`warm_up()`
        çağrısında) gerekip gerekmediğini söyler."""
        needs_reload = (
            settings.model != self._settings.model
            or settings.compute_type != self._settings.compute_type
            or settings.device != self._settings.device
        )
        with self._lock:
            self._settings = settings
            if needs_reload:
                self._model = None
                self._pipeline = None
                self._downgraded = False
                self._compute_type = settings.compute_type
        return needs_reload

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

    def warm_up(self) -> None:
        """Modeli yükler ve ilk gerçek isteğin yavaş olmaması için kısa bir çözümleme yapar."""
        if not self.is_loaded:
            self.load()
        if not self._settings.warm_up:
            return
        rng = np.random.default_rng(0)
        audio = (rng.standard_normal(int(SAMPLE_RATE * WARM_UP_SECONDS)) * 0.01).astype(np.float32)
        try:
            with self._lock:
                seg_iter, _info = self._model.transcribe(
                    audio, language=self._settings.language, beam_size=1, vad_filter=False
                )
                list(seg_iter)
        except Exception as exc:  # noqa: BLE001 - ısınma hatası uygulamayı durdurmamalı
            log.warning("STT ısınma çözümlemesi başarısız: %s", exc)
        else:
            log.info("STT ısınması tamamlandı")

    def _use_batching(self, audio: np.ndarray) -> bool:
        if not self._settings.batch_enabled:
            return False
        if not self._settings.vad_filter:
            # Toplu boru hattı konuşma aralıklarını VAD'den alır; VAD kapalıyken çalışmaz.
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
        s = self._settings
        # Tamamen sessiz kayıtta Whisper çağrılmaz: uydurma altyazı metni üretmesini engeller.
        # Sonda toplu boru hattı için yeniden kullanılabilmesi için sonuç saklanır (VAD iki kez çalışmaz).
        speech: list[dict] | bool = True
        if s.vad_filter:
            speech = self._speech_probe(audio, s)
            if not speech:
                raise SttError("Konuşma algılanmadı; mikrofon ve VAD eşiğini kontrol edin")
        if not self.is_loaded:
            self.load()
        lang = language or s.language
        kwargs = {
            "language": lang,
            "task": "transcribe",
            "beam_size": s.beam_size,
            "vad_filter": s.vad_filter,
            "vad_parameters": _vad_options(s),
            "no_speech_threshold": s.no_speech_threshold,
            "log_prob_threshold": s.log_prob_threshold,
            "hallucination_silence_threshold": s.hallucination_silence_threshold_s or None,
            "without_timestamps": True,  # kelime zamanları kullanılmıyor
            "initial_prompt": " ".join(p for p in (s.initial_prompt, self._prompt_terms) if p)
            or None,
            "hotwords": self._hotwords or None,
        }
        try:
            with self._lock:
                if self._use_batching(audio):
                    target = self._get_pipeline()
                    kwargs["batch_size"] = s.batch_size
                    if isinstance(speech, list):
                        kwargs["clip_timestamps"] = [
                            {"start": t["start"] / SAMPLE_RATE, "end": t["end"] / SAMPLE_RATE}
                            for t in speech
                        ]
                else:
                    target = self._model
                    kwargs["condition_on_previous_text"] = True
                seg_iter, info = target.transcribe(audio.astype(np.float32, copy=False), **kwargs)
                segments = tuple(
                    Segment(
                        seg.start,
                        seg.end,
                        seg.text.strip(),
                        no_speech_prob=float(getattr(seg, "no_speech_prob", 0.0)),
                        avg_logprob=float(getattr(seg, "avg_logprob", 0.0)),
                    )
                    for seg in seg_iter
                )
        except Exception as exc:
            raise SttError(f"Transkripsiyon hatası: {exc}") from exc
        if s.hallucination_filter:
            segments = filter_segments(
                segments,
                no_speech_threshold=s.no_speech_threshold,
                log_prob_threshold=s.log_prob_threshold,
            )
        text = " ".join(seg.text for seg in segments if seg.text).strip()
        return TranscriptResult(
            text=text,
            language=info.language,
            duration_s=float(info.duration),
            segments=segments,
        )
