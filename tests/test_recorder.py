import numpy as np
import pytest

from dikte.audio.recorder import AudioRecorder
from dikte.config import AudioSettings


class FakeStream:
    """sounddevice.InputStream taklidi: start() sonrası callback'i elle tetikleriz."""

    instances: list["FakeStream"] = []

    def __init__(
        self, *, callback, samplerate, channels, dtype, device, blocksize, finished_callback=None
    ):
        self.callback = callback
        self.finished_callback = finished_callback
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

    def finish(self):
        """PortAudio akışın bittiğini bildirir (cihaz çıkarıldı ya da stop() çağrıldı)."""
        if self.finished_callback is not None:
            self.finished_callback()


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


def test_callback_copies_reused_input_buffer(rec):
    """PortAudio aynı tamponu yeniden kullanır; kayıt bu tampona view tutmamalı."""
    rec.start()
    s = FakeStream.instances[-1]
    buffer = np.full(1600, 0.25, dtype=np.float32)
    s.push(buffer)
    buffer[:] = 1e30  # sürücü tamponu bir sonraki blokla ezer
    audio = rec.stop()
    assert np.isfinite(audio).all()
    assert audio == pytest.approx(np.full(1600, 0.25, dtype=np.float32))


# ---- stop/close sağlamlığı


def test_stop_closes_stream_even_if_stop_fails(qtbot):
    class StopFails(FakeStream):
        def stop(self):
            raise RuntimeError("PortAudio hatası")

    FakeStream.instances.clear()
    rec = AudioRecorder(AudioSettings(), stream_factory=StopFails)
    rec.start()
    rec.stop()
    assert FakeStream.instances[-1].closed and not rec.is_recording


# ---- cihaz adına göre seçim

_HOSTAPIS = [{"name": "MME"}, {"name": "Windows WASAPI"}]
_DEVICES = [
    {"name": "Hoparlör", "max_input_channels": 0, "hostapi": 0},
    {"name": "USB Mikrofon", "max_input_channels": 1, "hostapi": 0},
    {"name": "Dahili Mikrofon", "max_input_channels": 2, "hostapi": 0},
    {"name": "USB Mikrofon", "max_input_channels": 1, "hostapi": 1},
]


def _query():
    return _DEVICES, _HOSTAPIS


def test_list_input_devices_returns_only_inputs():
    from dikte.audio.recorder import InputDevice, list_input_devices

    devices = list_input_devices(query=_query)
    assert devices == [
        InputDevice(name="USB Mikrofon", index=1, hostapi="MME"),
        InputDevice(name="Dahili Mikrofon", index=2, hostapi="MME"),
        InputDevice(name="USB Mikrofon", index=3, hostapi="Windows WASAPI"),
    ]


def test_list_input_devices_query_failure_returns_empty(caplog):
    from dikte.audio.recorder import list_input_devices

    def boom():
        raise OSError("PortAudio yok")

    assert list_input_devices(query=boom) == []
    assert "PortAudio yok" in caplog.text


def test_device_name_resolved_to_index(qtbot):
    FakeStream.instances.clear()
    rec = AudioRecorder(
        AudioSettings(device_name="Dahili Mikrofon", device_index=1),
        stream_factory=FakeStream,
        device_probe=_query,
    )
    rec.start()
    assert FakeStream.instances[-1].device == 2  # ad, eski index'ten önceliklidir


def test_duplicate_names_prefer_wasapi_on_windows(qtbot, monkeypatch):
    import dikte.audio.recorder as mod

    monkeypatch.setattr(mod.sys, "platform", "win32")
    FakeStream.instances.clear()
    rec = AudioRecorder(
        AudioSettings(device_name="USB Mikrofon"), stream_factory=FakeStream, device_probe=_query
    )
    rec.start()
    assert FakeStream.instances[-1].device == 3


def test_duplicate_names_use_first_elsewhere(qtbot, monkeypatch):
    import dikte.audio.recorder as mod

    monkeypatch.setattr(mod.sys, "platform", "linux")
    FakeStream.instances.clear()
    rec = AudioRecorder(
        AudioSettings(device_name="USB Mikrofon"), stream_factory=FakeStream, device_probe=_query
    )
    rec.start()
    assert FakeStream.instances[-1].device == 1


def test_missing_device_name_falls_back_to_default_with_warning(qtbot):
    FakeStream.instances.clear()
    rec = AudioRecorder(
        AudioSettings(device_name="Kayıp Mikrofon", device_index=1),
        stream_factory=FakeStream,
        device_probe=_query,
    )
    warnings = []
    rec.warning.connect(warnings.append)
    rec.start()
    assert FakeStream.instances[-1].device is None
    assert warnings == [
        "Kayıtlı mikrofon bulunamadı (Kayıp Mikrofon); varsayılan mikrofon kullanılıyor."
    ]
    assert rec.is_recording


def test_empty_device_name_uses_device_index_without_query(qtbot):
    FakeStream.instances.clear()

    def no_query():
        raise AssertionError("ad boşken cihaz listesi sorgulanmamalı")

    rec = AudioRecorder(
        AudioSettings(device_index=4), stream_factory=FakeStream, device_probe=no_query
    )
    rec.start()
    assert FakeStream.instances[-1].device == 4


# ---- cihaz çıkarıldı


def test_stream_finishing_unexpectedly_emits_error(rec, qtbot):
    rec.start()
    errors = []
    rec.error.connect(errors.append)
    FakeStream.instances[-1].finish()  # cihaz çıkarıldı: PortAudio akışı kendisi bitirdi
    assert errors and "Mikrofon bağlantısı kesildi" in errors[0]


def test_finish_after_own_stop_is_silent(rec):
    rec.start()
    s = FakeStream.instances[-1]
    errors = []
    rec.error.connect(errors.append)
    rec.stop()
    s.finish()  # kendi stop() çağrımız da finished_callback'i tetikler
    assert errors == []


# ---- ölü mikrofon


def test_dead_mic_warns_once_after_threshold(qtbot):
    FakeStream.instances.clear()
    rec = AudioRecorder(AudioSettings(dead_mic_warn_s=1.0), stream_factory=FakeStream)
    warnings = []
    rec.warning.connect(warnings.append)
    rec.start()
    s = FakeStream.instances[-1]
    for _ in range(9):  # 0,9 sn tam sessizlik
        s.push(np.zeros(1600, dtype=np.float32))
    assert warnings == []
    for _ in range(20):
        s.push(np.zeros(1600, dtype=np.float32))
    assert warnings == [
        "Mikrofondan ses gelmiyor. Doğru mikrofonun seçili olduğunu ve sessize "
        "alınmadığını kontrol edin."
    ]


def test_dead_mic_not_reported_when_signal_present(qtbot):
    FakeStream.instances.clear()
    rec = AudioRecorder(AudioSettings(dead_mic_warn_s=1.0), stream_factory=FakeStream)
    warnings = []
    rec.warning.connect(warnings.append)
    rec.start()
    s = FakeStream.instances[-1]
    s.push(np.full(1600, 0.001, dtype=np.float32))  # oda gürültüsü: mikrofon canlı
    for _ in range(30):
        s.push(np.zeros(1600, dtype=np.float32))
    assert warnings == []


def test_dead_mic_check_disabled_with_zero(qtbot):
    FakeStream.instances.clear()
    rec = AudioRecorder(AudioSettings(dead_mic_warn_s=0), stream_factory=FakeStream)
    warnings = []
    rec.warning.connect(warnings.append)
    rec.start()
    s = FakeStream.instances[-1]
    for _ in range(100):
        s.push(np.zeros(1600, dtype=np.float32))
    assert warnings == []
