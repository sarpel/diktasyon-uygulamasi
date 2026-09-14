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


def make_engine():
    created = {}

    def factory(*a, **kw):
        m = FakeModel(*a, **kw)
        created["model"] = m
        return m

    return FasterWhisperEngine(SttSettings(), model_factory=factory), created


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

    eng = FasterWhisperEngine(SttSettings(), model_factory=bad_factory)
    with pytest.raises(SttError, match="CUDA yok"):
        eng.load()


@pytest.mark.gpu
def test_real_model_transcribes_silence_without_crash():
    eng = FasterWhisperEngine(SttSettings())
    eng.load()
    res = eng.transcribe(np.zeros(16000, dtype=np.float32))
    assert isinstance(res.text, str)
