from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, Signal

from dikte.audio.levels import bucketize, rms
from dikte.config import AudioSettings

log = logging.getLogger(__name__)
BLOCK_SIZE = 1600  # 100 ms @ 16 kHz
BUCKETS = 32
# Bunun altındaki RMS "hiç sinyal yok" sayılır: sessize alınmış/yanlış seçilmiş mikrofon tam
# sıfır (ya da ~1e-6) verir; sessiz bir odadaki canlı mikrofonun gürültüsü bile bunun üstündedir.
DEAD_MIC_FLOOR = 1e-4
DEAD_MIC_MESSAGE = (
    "Mikrofondan ses gelmiyor. Doğru mikrofonun seçili olduğunu ve sessize "
    "alınmadığını kontrol edin."
)
DEVICE_LOST_MESSAGE = (
    "Mikrofon bağlantısı kesildi; kayıt durduruldu. Mikrofonun takılı olduğunu kontrol "
    "edip yeniden deneyin."
)

DeviceQuery = Callable[[], tuple[list, list]]


def _default_stream_factory(*, wasapi_auto_convert: bool = False, **kwargs):
    import sounddevice as sd  # type: ignore[import-not-found]

    if wasapi_auto_convert:
        # WASAPI paylaşımlı modu yalnızca cihazın karışım hızını (çoğunlukla 48 kHz) kabul
        # eder; auto_convert olmadan 16 kHz akış "Invalid sample rate" ile açılmaz.
        kwargs["extra_settings"] = sd.WasapiSettings(auto_convert=True)
    return sd.InputStream(**kwargs)


def _default_device_query() -> tuple[list, list]:
    """(cihazlar, host API'leri) — sounddevice.query_devices/query_hostapis biçiminde."""
    import sounddevice as sd  # type: ignore[import-not-found]

    return list(sd.query_devices()), list(sd.query_hostapis())


@dataclass(frozen=True)
class InputDevice:
    name: str
    index: int
    hostapi: str  # ör. "Windows WASAPI", "MME", "ALSA"


def list_input_devices(query: DeviceQuery | None = None) -> list[InputDevice]:
    """Giriş kanalı olan ses cihazları (ayarlar arayüzü ve ada göre seçim için).
    Sorgu başarısız olursa boş liste döner (hata günlüğe yazılır)."""
    try:
        devices, hostapis = (query or _default_device_query)()
    except Exception:
        log.exception("ses cihazları listelenemedi")
        return []
    result: list[InputDevice] = []
    for index, d in enumerate(devices):
        if int(d.get("max_input_channels", 0)) <= 0:
            continue
        api_index = d.get("hostapi", -1)
        api = hostapis[api_index]["name"] if 0 <= api_index < len(hostapis) else ""
        result.append(InputDevice(name=str(d.get("name", "")), index=index, hostapi=api))
    return result


def _match_device(name: str, devices: list[InputDevice]) -> InputDevice | None:
    """Ada göre eşleşme: önce birebir, sonra büyük/küçük harf ve boşluk duyarsız. Aynı ad
    birden çok host API'de görünüyorsa Windows'ta WASAPI tercih edilir (düşük gecikme,
    paylaşımlı mod); diğer platformlarda ilk (en küçük index'li) eşleşme alınır."""
    candidates = [d for d in devices if d.name == name]
    if not candidates:
        key = name.strip().casefold()
        candidates = [d for d in devices if d.name.strip().casefold() == key]
    if not candidates:
        return None
    if sys.platform == "win32":
        for d in candidates:
            if "wasapi" in d.hostapi.casefold():
                return d
    return candidates[0]


class AudioRecorder(QObject):
    level_changed = Signal(float)
    buckets_changed = Signal(object)
    limit_reached = Signal()
    silence_reached = Signal()
    chunk_ready = Signal(object)
    error = Signal(str)
    warning = Signal(str)  # kaydı durdurmayan uyarılar (cihaz bulunamadı, ölü mikrofon)

    def __init__(
        self,
        settings: AudioSettings,
        stream_factory: Callable | None = None,
        parent=None,
        *,
        chunk_s: float = 0.0,
        max_chunk_s: float = 45.0,
        device_probe: DeviceQuery | None = None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._active_settings = settings  # süren kayıtta kullanılan sabit anlık görüntü
        self._factory = stream_factory or _default_stream_factory
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._total = 0
        self._chunk_samples = 0
        self._chunk_s = chunk_s
        self._max_chunk_s = max_chunk_s
        self._limit_hit = False
        self._speech_seen = False
        self._silent_samples = 0
        self._silence_hit = False
        self._lock = threading.Lock()
        self._device_probe = device_probe
        self._stream_token = 0  # finished_callback'in hangi akışa ait olduğunu ayırt eder
        self._active_token: int | None = None
        self._chunks_emitted = 0
        self._dead_samples = 0
        self._signal_seen = False
        self._dead_warned = False

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    @property
    def chunks_emitted(self) -> int:
        """Süren (ya da son `stop()` ile biten) kayıtta yayınlanan `chunk_ready` sayısı.
        Denetleyici, durdurma sonrası kuyrukta gecikip gelen parçaları beklemek için okur."""
        return self._chunks_emitted

    def _resolve_device(self, settings: AudioSettings) -> tuple[int | None, bool]:
        """Kayıtlı mikrofon adı → (güncel PortAudio index'i, WASAPI mi). Index'ler cihaz
        takılıp çıkınca kayar. Ad boşsa eski `device_index`, o da yoksa varsayılan (None)."""
        name = settings.device_name
        if not name:
            return settings.device_index, False
        found = _match_device(name, list_input_devices(self._device_probe))
        if found is not None:
            wasapi = sys.platform == "win32" and "wasapi" in found.hostapi.casefold()
            return found.index, wasapi
        log.warning("kayıtlı mikrofon bulunamadı: %s; varsayılan kullanılıyor", name)
        self.warning.emit(
            f"Kayıtlı mikrofon bulunamadı ({name}); varsayılan mikrofon kullanılıyor."
        )
        return None, False

    def _open_stream(self, device: int | None, wasapi: bool, token: int):
        extra = {"wasapi_auto_convert": True} if wasapi else {}
        return self._factory(
            callback=self._on_audio,
            samplerate=self._active_settings.sample_rate,
            channels=1,
            dtype="float32",
            device=device,
            blocksize=BLOCK_SIZE,
            finished_callback=lambda: self._on_stream_finished(token),
            **extra,
        )

    def update_settings(self, settings: AudioSettings) -> None:
        """Süren kayıt etkilenmez; yeni cihaz/parametreler bir sonraki `start()`'ta geçerli olur."""
        self._settings = settings

    def set_chunking(self, chunk_s: float, max_chunk_s: float) -> None:
        """Canlı parça parça çözümleme parametrelerini günceller (`chunk_s=0` kapatır)."""
        self._chunk_s = chunk_s
        self._max_chunk_s = max_chunk_s

    def start(self) -> None:
        if self._stream is not None:
            return
        self._active_settings = self._settings  # bu oturum boyunca sabit
        self._chunks, self._total, self._limit_hit = [], 0, False
        self._chunk_samples = 0
        self._speech_seen, self._silent_samples, self._silence_hit = False, 0, False
        self._chunks_emitted = 0
        self._dead_samples, self._signal_seen, self._dead_warned = 0, False, False
        self._stream_token += 1
        token = self._stream_token
        stream = None
        try:
            device, wasapi = self._resolve_device(self._active_settings)
            try:
                stream = self._open_stream(device, wasapi, token)
            except Exception as exc:
                if device is None:
                    raise
                # Seçili cihaz açılamadı (ör. desteklemediği örnekleme hızı): dikte hiç
                # başlamamaktansa varsayılan mikrofonla sürer ve kullanıcı uyarılır.
                log.exception("seçili mikrofon açılamadı; varsayılan deneniyor")
                label = self._active_settings.device_name or f"#{device}"
                self.warning.emit(
                    f"Seçili mikrofon açılamadı ({label}: {exc}); varsayılan mikrofon kullanılıyor."
                )
                stream = self._open_stream(None, False, token)
            self._active_token = token
            stream.start()
            self._stream = stream
        except Exception as exc:  # sounddevice.PortAudioError vb.
            self._stream = None
            self._active_token = None
            if stream is not None:
                # Nesne oluşturuldu ama start() başarısız oldu: donanım tutamacı sızmasın.
                try:
                    stream.close()
                except Exception:
                    log.exception("başarısız stream kapatılırken hata")
            log.exception("mikrofon açılamadı")
            self.error.emit(f"Mikrofon açılamadı: {exc}")

    def stop(self) -> np.ndarray:
        stream, self._stream = self._stream, None
        self._active_token = None  # bundan sonraki finished_callback bizim durdurmamızdır
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                log.exception("stream durdurulurken hata")
            finally:
                # stop() başarısız olsa bile PortAudio tutamacı sızmasın.
                try:
                    stream.close()
                except Exception:
                    log.exception("stream kapatılırken hata")
        with self._lock:
            chunks, self._chunks = self._chunks, []
            self._total = 0
            self._chunk_samples = 0
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)

    def _on_stream_finished(self, token: int) -> None:
        """PortAudio iş parçacığından çağrılır. Akış biz `stop()` demeden bittiyse (cihaz
        çıkarıldı, sürücü hatası) kullanıcı bilgilendirilir; `error` kuyruklu bağlantıyla
        GUI iş parçacığına ulaşır ve denetleyici RECORDING'den çıkar."""
        if token != self._active_token:
            return
        self._active_token = None
        log.error("ses akışı beklenmedik biçimde sonlandı (cihaz çıkarılmış olabilir)")
        self.error.emit(DEVICE_LOST_MESSAGE)

    def _track_dead_mic(self, level: float, n: int) -> None:
        warn_s = self._active_settings.dead_mic_warn_s
        if warn_s <= 0 or self._signal_seen or self._dead_warned:
            return
        if level >= DEAD_MIC_FLOOR:
            self._signal_seen = True
            return
        self._dead_samples += n
        if self._dead_samples >= warn_s * self._active_settings.sample_rate:
            self._dead_warned = True
            log.warning("mikrofondan %.1f sn boyunca hiç sinyal gelmedi", warn_s)
            self.warning.emit(DEAD_MIC_MESSAGE)

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:
            # input overflow zararsızdır (bir blok kaybı); cihaz kaybı finished_callback'le gelir.
            log.warning("audio status: %s", status)
        # PortAudio giriş tamponunu her geri çağırmada yeniden kullanır; view saklamak
        # sonradan üzerine yazılan (bozuk/çöp) ses verisi demektir. Bu yüzden kopya alınır.
        frame: np.ndarray | None = np.array(indata, dtype=np.float32).reshape(-1)
        limit = self._active_settings.max_seconds * self._active_settings.sample_rate  # 0=sınırsız
        first_hit = False
        level = 0.0
        chunk_to_emit: np.ndarray | None = None
        with self._lock:
            if limit > 0:
                room = limit - self._total
                if room <= 0:
                    first_hit, self._limit_hit = not self._limit_hit, True
                    frame = None
                else:
                    frame = frame[:room]
            if frame is not None:
                self._chunks.append(frame)
                self._total += frame.shape[0]
                self._chunk_samples += frame.shape[0]
                # Sınırı tam dolduran blok da kaydı hemen bitirir (bir blok gecikmeden).
                if 0 < limit <= self._total and not self._limit_hit:
                    first_hit, self._limit_hit = True, True
                level = rms(frame)
                if self._chunk_s > 0:
                    chunk_to_emit = self._maybe_flush_chunk(level)
        # chunk_ready, RECORDING durumundayken tüketilmesi için durdurma sinyallerinden
        # (limit_reached/silence_reached) ÖNCE yayınlanır. Qt'nin kuyruklu bağlantıları aynı
        # alıcı için FIFO sırasını korur, bu yüzden emit sırası GUI iş parçacığındaki işlem
        # sırasını belirler; tersi olursa son parça durdurma sonrası atılırdı.
        if chunk_to_emit is not None:
            self._chunks_emitted += 1  # yalnızca bu iş parçacığı yazar; stop() sonra okur
            self.chunk_ready.emit(chunk_to_emit)
        if first_hit:
            self.limit_reached.emit()
        if frame is None:
            return
        self._track_silence(level, frame.shape[0])
        self._track_dead_mic(level, frame.shape[0])
        self.level_changed.emit(level)
        self.buckets_changed.emit(bucketize(frame, BUCKETS))

    def _maybe_flush_chunk(self, level: float) -> np.ndarray | None:
        """Kilit altında çağrılır. Toplanan süre `chunk_s`i geçip blok sessizse, ya da
        `max_chunk_s`e ulaşılmışsa (sessizlikten bağımsız sert kesim) parçayı boşaltır."""
        duration_s = self._chunk_samples / self._active_settings.sample_rate
        should_flush = duration_s >= self._max_chunk_s or (
            duration_s >= self._chunk_s and level < self._active_settings.silence_threshold
        )
        if not should_flush or not self._chunks:
            return None
        chunk, self._chunks = self._chunks, []
        self._chunk_samples = 0
        return np.concatenate(chunk).astype(np.float32, copy=False)

    def _track_silence(self, level: float, n: int) -> None:
        stop_s = self._active_settings.silence_stop_s
        thr = self._active_settings.silence_threshold
        if stop_s <= 0 or self._silence_hit:
            return
        if level > thr * 3:
            self._speech_seen, self._silent_samples = True, 0
            return
        if not self._speech_seen:
            return
        self._silent_samples += n
        if self._silent_samples >= stop_s * self._active_settings.sample_rate:
            self._silence_hit = True
            self.silence_reached.emit()
