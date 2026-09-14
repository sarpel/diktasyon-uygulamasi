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

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
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
    )
    return eng, created


def long_audio(seconds: float) -> np.ndarray:
    return np.zeros(int(16000 * seconds), dtype=np.float32)


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

    eng = FasterWhisperEngine(
        SttSettings(), model_factory=bad_factory, cuda_probe=lambda: 1
    )
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
def test_real_model_transcribes_silence_without_crash():
    eng = FasterWhisperEngine(SttSettings())
    eng.load()
    res = eng.transcribe(np.zeros(16000, dtype=np.float32))
    assert isinstance(res.text, str)


@pytest.mark.gpu
def test_real_batched_pipeline_handles_long_audio():
    """Toplu boru hattının gerçek API'siyle uyumu (kwargs kabulü) doğrulanır."""
    eng = FasterWhisperEngine(SttSettings(batch_threshold_s=5.0, batch_size=4))
    res = eng.transcribe(np.zeros(16000 * 30, dtype=np.float32))
    assert isinstance(res.text, str)
