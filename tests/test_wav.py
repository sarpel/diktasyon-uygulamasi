import wave

import numpy as np
import pytest

from dikte.audio.wav import load_wav, save_wav


def test_save_writes_16k_mono_int16_and_roundtrips(tmp_path):
    p = tmp_path / "failed" / "last.wav"
    audio = np.linspace(-1.0, 1.0, 16000, dtype=np.float32)
    save_wav(p, audio)
    with wave.open(str(p), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
        assert w.getnframes() == 16000
    back = load_wav(p)
    assert back.dtype == np.float32 and back.shape == (16000,)
    assert np.allclose(back, audio, atol=1 / 32767 + 1e-6)


def test_save_clips_out_of_range_samples(tmp_path):
    p = tmp_path / "a.wav"
    save_wav(p, np.array([2.0, -2.0], dtype=np.float32))
    assert load_wav(p) == pytest.approx([1.0, -1.0], abs=1e-4)


def test_load_rejects_other_sample_rates(tmp_path):
    p = tmp_path / "b.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x00" * 10)
    with pytest.raises(ValueError, match="16000"):
        load_wav(p)


def test_failed_audio_path_is_under_app_data(monkeypatch, tmp_path):
    from dikte import paths

    monkeypatch.setattr(paths, "app_data_dir", lambda: tmp_path)
    p = paths.failed_audio_path()
    assert p == tmp_path / "failed" / "last.wav" and p.parent.is_dir()
