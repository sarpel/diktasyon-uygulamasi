import numpy as np

from dikte.audio.levels import bucketize, rms


def test_rms_of_silence_is_zero():
    assert rms(np.zeros(1600, dtype=np.float32)) == 0.0


def test_rms_of_full_scale_sine_is_about_0_7():
    t = np.linspace(0, 1, 16000, dtype=np.float32)
    assert abs(rms(np.sin(2 * np.pi * 440 * t)) - 0.707) < 0.01


def test_rms_is_clamped_to_one():
    assert rms(np.full(100, 5.0, dtype=np.float32)) == 1.0


def test_bucketize_returns_requested_count():
    frame = np.random.default_rng(0).standard_normal(1600).astype(np.float32) * 0.1
    b = bucketize(frame, 32)
    assert len(b) == 32 and all(0.0 <= v <= 1.0 for v in b)


def test_bucketize_empty_frame_returns_zeros():
    assert bucketize(np.zeros(0, dtype=np.float32), 8) == (0.0,) * 8
