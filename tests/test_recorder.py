import numpy as np
import pytest

from dikte.audio.recorder import AudioRecorder
from dikte.config import AudioSettings


class FakeStream:
    """sounddevice.InputStream taklidi: start() sonrası callback'i elle tetikleriz."""

    instances: list["FakeStream"] = []

    def __init__(self, *, callback, samplerate, channels, dtype, device, blocksize):
        self.callback = callback
        self.samplerate, self.channels, self.dtype, self.device = (
            samplerate,
            channels,
            dtype,
            device,
        )
        self.started = self.stopped = self.closed = False
        FakeStream.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True

    def push(self, frame: np.ndarray):
        self.callback(frame.reshape(-1, 1), len(frame), None, None)


@pytest.fixture
def rec(qtbot):
    FakeStream.instances.clear()
    r = AudioRecorder(AudioSettings(), stream_factory=FakeStream)
    return r


def test_start_opens_16k_mono_float32_stream(rec):
    rec.start()
    s = FakeStream.instances[-1]
    assert (s.samplerate, s.channels, s.dtype, s.started) == (16000, 1, "float32", True)
    assert rec.is_recording


def test_stop_returns_concatenated_audio(rec):
    rec.start()
    s = FakeStream.instances[-1]
    s.push(np.ones(1600, dtype=np.float32) * 0.5)
    s.push(np.ones(800, dtype=np.float32) * -0.5)
    audio = rec.stop()
    assert audio.dtype == np.float32 and audio.shape == (2400,)
    assert s.stopped and s.closed and not rec.is_recording


def test_level_signal_emitted_per_frame(rec, qtbot):
    rec.start()
    with qtbot.waitSignal(rec.level_changed, timeout=1000) as blocker:
        FakeStream.instances[-1].push(np.ones(1600, dtype=np.float32) * 0.5)
    assert abs(blocker.args[0] - 0.5) < 1e-6


def test_stop_without_start_returns_empty(rec):
    assert rec.stop().shape == (0,)


def test_max_seconds_truncates(rec):
    rec = AudioRecorder(AudioSettings(max_seconds=5), stream_factory=FakeStream)
    rec.start()
    s = FakeStream.instances[-1]
    for _ in range(70):  # 70 * 1600 = 112000 örnek = 7 s
        s.push(np.zeros(1600, dtype=np.float32))
    assert rec.stop().shape[0] == 5 * 16000
