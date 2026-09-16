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


def test_update_settings_applies_on_next_start(rec):
    rec.update_settings(AudioSettings(device_index=3))
    rec.start()
    assert FakeStream.instances[-1].device == 3


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


def test_unlimited_recording_keeps_all_audio(qtbot):
    rec = AudioRecorder(AudioSettings(max_seconds=0), stream_factory=FakeStream)
    rec.start()
    s = FakeStream.instances[-1]
    for _ in range(50):  # 50 × 1600 = 80 000 örnek = 5 sn
        s.push(np.ones(1600, dtype=np.float32) * 0.1)
    assert rec.stop().shape[0] == 80_000


def test_limit_emits_signal_once_and_keeps_everything_up_to_limit(qtbot):
    rec = AudioRecorder(AudioSettings(max_seconds=1), stream_factory=FakeStream)
    fired = []
    rec.limit_reached.connect(lambda: fired.append(True))
    rec.start()
    s = FakeStream.instances[-1]
    for _ in range(12):  # 19 200 örnek > 16 000
        s.push(np.ones(1600, dtype=np.float32) * 0.1)
    assert fired == [True]
    assert rec.stop().shape[0] == 16_000


def test_block_that_exactly_fills_the_limit_stops_recording_immediately(qtbot):
    """16 000. örneği getiren blok sınırı tam doldurur; sinyal bir sonraki bloğu beklemez."""
    rec = AudioRecorder(AudioSettings(max_seconds=1), stream_factory=FakeStream)
    fired = []
    rec.limit_reached.connect(lambda: fired.append(True))
    rec.start()
    s = FakeStream.instances[-1]
    for _ in range(10):  # 10 × 1600 = 16 000 örnek = tam sınır
        s.push(np.ones(1600, dtype=np.float32) * 0.1)
    assert fired == [True]
    assert rec.stop().shape[0] == 16_000


def test_silence_stop_fires_once_after_speech(qtbot):
    rec = AudioRecorder(AudioSettings(silence_stop_s=1.0), stream_factory=FakeStream)
    fired = []
    rec.silence_reached.connect(lambda: fired.append(True))
    rec.start()
    s = FakeStream.instances[-1]
    for _ in range(15):  # 1,5 sn sessizlik ama henüz konuşma yok → sinyal yok
        s.push(np.zeros(1600, dtype=np.float32))
    assert fired == []
    s.push(np.ones(1600, dtype=np.float32) * 0.2)  # konuşma
    for _ in range(12):  # 1,2 sn sessizlik
        s.push(np.zeros(1600, dtype=np.float32))
    assert fired == [True]


def test_silence_stop_disabled_by_default(qtbot):
    rec = AudioRecorder(AudioSettings(), stream_factory=FakeStream)
    fired = []
    rec.silence_reached.connect(lambda: fired.append(True))
    rec.start()
    s = FakeStream.instances[-1]
    s.push(np.ones(1600, dtype=np.float32) * 0.2)
    for _ in range(100):
        s.push(np.zeros(1600, dtype=np.float32))
    assert fired == []


def test_chunking_disabled_by_default(rec):
    rec.start()
    s = FakeStream.instances[-1]
    fired = []
    rec.chunk_ready.connect(lambda audio: fired.append(audio))
    for _ in range(200):
        s.push(np.zeros(1600, dtype=np.float32))
    assert fired == []


def test_chunk_ready_fires_after_min_duration_and_silence(qtbot):
    rec = AudioRecorder(AudioSettings(), stream_factory=FakeStream, chunk_s=1.0, max_chunk_s=45.0)
    fired = []
    rec.chunk_ready.connect(lambda audio: fired.append(audio))
    rec.start()
    s = FakeStream.instances[-1]
    for _ in range(12):  # 12 * 1600 = 19 200 örnek = 1,2 sn konuşma
        s.push(np.ones(1600, dtype=np.float32) * 0.1)
    assert fired == []  # süre yeter ama sessizlik yok
    s.push(np.zeros(1600, dtype=np.float32))  # sessiz blok: süre + sessizlik birlikte sağlanır
    assert len(fired) == 1
    assert fired[0].shape == (13 * 1600,)
    s.push(np.ones(1600, dtype=np.float32) * 0.2)
    s.push(np.ones(1600, dtype=np.float32) * 0.2)
    audio = rec.stop()
    assert audio.shape == (2 * 1600,)  # yalnızca son parçadan sonraki kuyruk döner


def test_chunk_ready_fires_on_max_chunk_s_even_without_silence(qtbot):
    rec = AudioRecorder(AudioSettings(), stream_factory=FakeStream, chunk_s=1.0, max_chunk_s=2.0)
    fired = []
    rec.chunk_ready.connect(lambda audio: fired.append(audio))
    rec.start()
    s = FakeStream.instances[-1]
    for _ in range(20):  # 20 * 1600 = 32 000 örnek = 2,0 sn, hiç sessizlik yok
        s.push(np.ones(1600, dtype=np.float32) * 0.1)
    assert len(fired) == 1
    assert fired[0].shape == (32_000,)


def test_set_chunking_updates_parameters(rec):
    rec.set_chunking(1.0, 45.0)
    rec.start()
    s = FakeStream.instances[-1]
    fired = []
    rec.chunk_ready.connect(lambda audio: fired.append(audio))
    for _ in range(11):
        s.push(np.ones(1600, dtype=np.float32) * 0.1)
    s.push(np.zeros(1600, dtype=np.float32))
    assert len(fired) == 1
