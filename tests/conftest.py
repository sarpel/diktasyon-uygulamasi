import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _FakeInputStream:
    """`sounddevice.InputStream` taklidi: bu makinede/CI'da gerçek mikrofon donanımı
    olmayabilir. `AudioRecorder`'ı doğrudan `stream_factory=` ile kuran testler kendi
    sahtelerini enjekte eder; bu yalnızca `build_app()` üzerinden gerçek fabrikayı
    kullanan (app.py) testler içindir — AGENTS.md'nin "her donanım erişimi enjekte
    edilebilir olmalı" kuralı gereği donanım yokluğu testleri kırmamalı."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _fake_default_audio_device(monkeypatch):
    monkeypatch.setattr(
        "dikte.audio.recorder._default_stream_factory", lambda **kwargs: _FakeInputStream()
    )


def _has_cuda() -> bool:
    try:
        import ctranslate2  # type: ignore[import-not-found]

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def pytest_runtest_setup(item):
    if "gpu" in item.keywords and not _has_cuda():
        pytest.skip("CUDA yok")
    if "win" in item.keywords and sys.platform != "win32":
        pytest.skip("yalnızca Windows")
