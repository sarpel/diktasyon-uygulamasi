from types import SimpleNamespace

import numpy as np
import pytest

from dikte.config import SttSettings
from dikte.stt.engine import FasterWhisperEngine, SttError
from dikte.stt.result import TranscriptResult


class FakeModel:
    def __init__(self, *args, **kwargs):
        self.init_args, self.init_kwargs = args, kwargs
        self.calls = []
        self.audios = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        self.audios.append(audio)
        segs = [
            SimpleNamespace(start=0.0, end=1.2, text=" merhaba"),
            SimpleNamespace(start=1.2, end=2.0, text=" dünya"),
        ]
        info = SimpleNamespace(language="tr", duration=2.0)
        return iter(segs), info


class FakePipeline:
    """BatchedInferencePipeline yerine geçer."""

    def __init__(self, model):
        self.model = model
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        return self.model.transcribe(audio, **kwargs)


def make_engine(settings: SttSettings | None = None):
    created = {}

    def factory(*a, **kw):
        m = FakeModel(*a, **kw)
        created["model"] = m
        return m

    def pipeline_factory(model):
        p = FakePipeline(model)
        created["pipeline"] = p
        return p

    eng = FasterWhisperEngine(
        settings or SttSettings(),
        model_factory=factory,
        pipeline_factory=pipeline_factory,
        cuda_probe=lambda: 1,
        speech_probe=lambda audio, s: True,  # gerçek VAD yerine: sessizlik testleri ayrı
    )
    return eng, created


def long_audio(seconds: float) -> np.ndarray:
    return np.zeros(int(16000 * seconds), dtype=np.float32)


def test_update_settings_reloads_only_on_model_change():
    eng, created = make_engine()
    eng.load()
    assert eng.update_settings(SttSettings(beam_size=1)) is False and eng.is_loaded
    assert eng.update_settings(SttSettings(model="small")) is True and not eng.is_loaded
    eng.load()
    assert created["model"].init_args[0] == "small"


def test_update_settings_changes_transcribe_kwargs():
    eng, created = make_engine()
    eng.update_settings(SttSettings(beam_size=2))
    eng.transcribe(np.zeros(16000, dtype=np.float32))
    assert created["model"].calls[0]["beam_size"] == 2


def test_set_dictionary_adds_hotwords_and_prompt_terms():
    eng, created = make_engine()
    eng.set_dictionary("a, b", "Terimler: a, b")
    eng.transcribe(np.zeros(16000, dtype=np.float32))
    call = created["model"].calls[0]
    assert call["hotwords"] == "a, b"
    assert call["initial_prompt"].endswith("Terimler: a, b")


def test_load_creates_model_with_settings():
    eng, created = make_engine()
    assert not eng.is_loaded
    eng.load()
    m = created["model"]
    assert m.init_args[0] == "large-v3-turbo"
    assert m.init_kwargs["device"] == "cuda" and m.init_kwargs["compute_type"] == "float16"
    assert eng.is_loaded


def test_transcribe_joins_segments_and_strips():
    eng, created = make_engine()
    eng.load()
    res = eng.transcribe(np.zeros(16000, dtype=np.float32))
    assert isinstance(res, TranscriptResult)
    assert res.text == "merhaba dünya" and res.language == "tr"
    assert len(res.segments) == 2 and res.segments[0].text == "merhaba"
    kw = created["model"].calls[0]
    assert kw["language"] == "tr" and kw["vad_filter"] is True and kw["beam_size"] == 5


def test_transcribe_autoloads():
    eng, _ = make_engine()
    assert eng.transcribe(np.zeros(16000, dtype=np.float32)).text == "merhaba dünya"


def test_transcribe_empty_audio_raises():
    eng, _ = make_engine()
    with pytest.raises(SttError):
        eng.transcribe(np.zeros(0, dtype=np.float32))


def test_load_failure_wraps_error():
    def bad_factory(*a, **kw):
        raise RuntimeError("CUDA yok")

    eng = FasterWhisperEngine(SttSettings(), model_factory=bad_factory, cuda_probe=lambda: 1)
    with pytest.raises(SttError, match="CUDA yok"):
        eng.load()


def test_load_without_gpu_raises_and_does_not_fall_back():
    eng = FasterWhisperEngine(
        SttSettings(),
        model_factory=lambda *a, **kw: pytest.fail("GPU yokken model yüklenmemeli"),
        cuda_probe=lambda: 0,
    )
    with pytest.raises(SttError, match="GPU"):
        eng.load()
    assert not eng.is_loaded


def test_settings_reject_cpu_device():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SttSettings(device="cpu")


def test_short_audio_uses_plain_model():
    eng, created = make_engine()
    eng.transcribe(long_audio(10))
    assert "pipeline" not in created
    assert "batch_size" not in created["model"].calls[0]


def test_long_audio_uses_batched_pipeline():
    eng, created = make_engine(SttSettings(batch_threshold_s=60.0, batch_size=8))
    eng.transcribe(long_audio(90))
    assert created["pipeline"].calls[0]["batch_size"] == 8
    assert created["pipeline"].calls[0]["language"] == "tr"


def test_batching_can_be_disabled():
    eng, created = make_engine(SttSettings(batch_enabled=False, batch_threshold_s=1.0))
    eng.transcribe(long_audio(90))
    assert "pipeline" not in created


def test_pipeline_is_created_once():
    eng, created = make_engine(SttSettings(batch_threshold_s=5.0))
    eng.transcribe(long_audio(10))
    first = created["pipeline"]
    eng.transcribe(long_audio(10))
    assert created["pipeline"] is first and len(first.calls) == 2


@pytest.mark.gpu
def test_real_silence_is_rejected_before_the_model_runs():
    """Sessiz kayıt Whisper'a hiç gitmez; aksi hâlde uydurma altyazı metni üretirdi."""
    eng = FasterWhisperEngine(
        SttSettings(), model_factory=lambda *a, **kw: pytest.fail("sessizlikte model yüklenmemeli")
    )
    with pytest.raises(SttError, match="Konuşma algılanmadı"):
        eng.transcribe(np.zeros(16000, dtype=np.float32))


@pytest.mark.gpu
def test_real_silero_probe_rejects_silence():
    from dikte.stt.engine import _default_speech_probe

    assert not _default_speech_probe(np.zeros(32_000, dtype=np.float32), SttSettings())


@pytest.mark.gpu
def test_real_batched_pipeline_handles_long_audio():
    """Toplu boru hattının gerçek API'siyle uyumu (kwargs kabulü) doğrulanır."""
    eng = FasterWhisperEngine(
        SttSettings(batch_threshold_s=5.0, batch_size=4),
        speech_probe=lambda audio, s: True,  # sessizlik ön-kontrolünü atla, kwargs'ı sına
    )
    res = eng.transcribe(np.zeros(16000 * 30, dtype=np.float32))
    assert isinstance(res.text, str)


def make_engine_with_types(supported, settings=None):
    created = {}

    def factory(*a, **kw):
        created["kwargs"] = kw
        return FakeModel(*a, **kw)

    eng = FasterWhisperEngine(
        settings or SttSettings(),
        model_factory=factory,
        cuda_probe=lambda: 1,
        supported_types_probe=lambda: set(supported),
        speech_probe=lambda audio, s: True,
    )
    return eng, created


def test_active_model_reflects_construction_settings():
    eng, _ = make_engine(SttSettings(model="large-v3"))
    assert eng.active_model == "large-v3"


def test_configured_compute_type_is_used_when_supported():
    eng, created = make_engine_with_types({"float16", "float32"})
    eng.load()
    assert created["kwargs"]["compute_type"] == "float16"


def test_unsupported_compute_type_falls_back_to_supported_one():
    eng, created = make_engine_with_types({"float32"})  # Maxwell/Pascal: fp16 yok
    eng.load()
    assert created["kwargs"]["compute_type"] == "float32"


def test_fallback_prefers_int8_float16_over_float32():
    eng, created = make_engine_with_types({"int8_float16", "float32"})
    eng.load()
    assert created["kwargs"]["compute_type"] == "int8_float16"


def test_no_supported_type_raises():
    eng, _ = make_engine_with_types(set())
    with pytest.raises(SttError, match="compute_type"):
        eng.load()


def test_probe_failure_does_not_block_load():
    def boom():
        raise RuntimeError("sorgulanamadı")

    eng = FasterWhisperEngine(
        SttSettings(),
        model_factory=lambda *a, **kw: FakeModel(*a, **kw),
        cuda_probe=lambda: 1,
        supported_types_probe=boom,
    )
    eng.load()
    assert eng.is_loaded


def test_warm_up_runs_one_dummy_transcribe():
    eng, created = make_engine()
    eng.warm_up()
    model = created["model"]
    assert len(model.calls) == 1
    audio = model.audios[0]
    assert audio.dtype == np.float32 and audio.shape[0] == 16_000
    assert model.calls[0]["beam_size"] == 1 and model.calls[0]["vad_filter"] is False


def test_warm_up_swallows_transcribe_errors(caplog):
    class FailingModel(FakeModel):
        def transcribe(self, audio, **kwargs):
            raise RuntimeError("cuDNN patladı")

    eng = FasterWhisperEngine(
        SttSettings(), model_factory=lambda *a, **kw: FailingModel(*a, **kw), cuda_probe=lambda: 1
    )
    eng.warm_up()  # yükseltmez
    assert "ısınma" in caplog.text.lower()


def test_warm_up_skipped_when_disabled():
    eng, created = make_engine(SttSettings(warm_up=False))
    eng.warm_up()
    assert eng.is_loaded and created["model"].calls == []


def test_silent_audio_raises_without_calling_model():
    eng, created = make_engine()
    eng._speech_probe = lambda audio, s: False
    with pytest.raises(SttError, match="Konuşma algılanmadı"):
        eng.transcribe(np.zeros(16000, dtype=np.float32))
    assert "model" not in created


def test_silence_check_skipped_when_vad_disabled():
    eng, _ = make_engine(SttSettings(vad_filter=False))
    eng._speech_probe = lambda audio, s: pytest.fail("VAD kapalıyken sorgulanmamalı")
    assert eng.transcribe(np.zeros(16000, dtype=np.float32)).text == "merhaba dünya"


def test_transcribe_passes_vad_and_hallucination_kwargs():
    eng, created = make_engine()
    eng.transcribe(np.ones(16000, dtype=np.float32) * 0.1)
    kw = created["model"].calls[0]
    assert kw["vad_parameters"] == {
        "threshold": 0.5,
        "min_silence_duration_ms": 1000,
        "speech_pad_ms": 300,
    }
    assert kw["no_speech_threshold"] == 0.6 and kw["log_prob_threshold"] == -1.0
    assert kw["hallucination_silence_threshold"] == 2.0 and kw["without_timestamps"] is True


def test_zero_hallucination_threshold_becomes_none():
    eng, created = make_engine(SttSettings(hallucination_silence_threshold_s=0))
    eng.transcribe(np.ones(16000, dtype=np.float32) * 0.1)
    assert created["model"].calls[0]["hallucination_silence_threshold"] is None


class HallucinatingModel(FakeModel):
    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        self.audios.append(audio)
        segs = [
            SimpleNamespace(
                start=0.0, end=1.0, text="Merhaba dünya", no_speech_prob=0.05, avg_logprob=-0.3
            ),
            SimpleNamespace(
                start=1.0, end=2.0, text="Altyazı M.K.", no_speech_prob=0.3, avg_logprob=-0.9
            ),
        ]
        return iter(segs), SimpleNamespace(language="tr", duration=2.0)


def _hallucinating_engine(settings=None):
    return FasterWhisperEngine(
        settings or SttSettings(),
        model_factory=lambda *a, **kw: HallucinatingModel(*a, **kw),
        cuda_probe=lambda: 1,
        speech_probe=lambda audio, s: True,
    )


def test_hallucinated_segments_removed():
    eng = _hallucinating_engine()
    assert eng.transcribe(np.ones(16000, dtype=np.float32) * 0.1).text == "Merhaba dünya"


def test_hallucination_filter_can_be_disabled():
    eng = _hallucinating_engine(SttSettings(hallucination_filter=False))
    assert "Altyazı M.K." in eng.transcribe(np.ones(16000, dtype=np.float32) * 0.1).text


def test_segment_confidences_are_recorded():
    eng = _hallucinating_engine(SttSettings(hallucination_filter=False))
    segments = eng.transcribe(np.ones(16000, dtype=np.float32) * 0.1).segments
    assert segments[0].no_speech_prob == 0.05 and segments[0].avg_logprob == -0.3


def test_batching_is_skipped_when_vad_disabled():
    """BatchedInferencePipeline clip_timestamps için VAD ister; kapalıyken düz model kullanılır."""
    eng, created = make_engine(SttSettings(vad_filter=False, batch_threshold_s=1.0))
    eng.transcribe(long_audio(30))
    assert "pipeline" not in created


def test_batched_path_reuses_probe_timestamps_in_seconds():
    settings = SttSettings(batch_threshold_s=5)
    created = {}
    eng = FasterWhisperEngine(
        settings,
        model_factory=lambda *a, **kw: created.setdefault("model", FakeModel(*a, **kw)),
        pipeline_factory=lambda m: created.setdefault("pipeline", FakePipeline(m)),
        cuda_probe=lambda: 1,
        speech_probe=lambda audio, s: [{"start": 0, "end": 16000}, {"start": 32000, "end": 48000}],
    )
    eng.transcribe(long_audio(10))
    kw = created["pipeline"].calls[0]
    assert kw["clip_timestamps"] == [{"start": 0.0, "end": 1.0}, {"start": 2.0, "end": 3.0}]


def test_short_path_does_not_pass_clip_timestamps():
    eng, created = make_engine()
    eng.transcribe(np.zeros(16000, dtype=np.float32))
    assert "clip_timestamps" not in created["model"].calls[0]
