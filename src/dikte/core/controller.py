"""`DictationController`: kayıt → STT → LLM düzeltmesi → sonuç akışını yöneten durum makinesi."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal, Slot

from dikte.audio.recorder import DEVICE_LOST_MESSAGE
from dikte.config import AppProfile, Settings
from dikte.core.state import DictationState, Session
from dikte.core.workers import run_in_pool
from dikte.llm import prompts, tasks
from dikte.llm.diff import word_changes
from dikte.llm.provider import LlmProvider
from dikte.stt.engine import SttEngine
from dikte.stt.result import NO_SPEECH_MESSAGE, TranscriptResult
from dikte.text.commands import apply_commands, is_undo_command
from dikte.text.dictionary import apply_compiled, compile_rules, hotwords, prompt_terms

log = logging.getLogger(__name__)
# Durdurma anında kayıtçının kestiği ama kuyruklu sinyali henüz gelmemiş parçalar için
# azami bekleme; normalde milisaniyeler içinde gelir, bu yalnızca takılmaya karşı güvence.
LATE_CHUNK_TIMEOUT_MS = 3000
RETRY_HINT = (
    " Ses kaydı saklandı; tepsideki “Başarısız kaydı yeniden dene” ile tekrar deneyebilirsiniz."
)


def _default_audio_loader(path: str) -> np.ndarray:
    from faster_whisper import decode_audio

    # split_stereo=False (varsayılan) tek kanal döndürür; asarray yalnızca tipi netleştirir.
    return np.asarray(decode_audio(path, sampling_rate=16000), dtype=np.float32)


class DictationController(QObject):
    """Dikte durum makinesi: IDLE → RECORDING → TRANSCRIBING → (CORRECTING) → RESULT.

    Tüm kamu yöntemleri GUI iş parçacığından çağrılır; STT/LLM işleri thread havuzunda
    çalışır ve sonuçları sinyalle geri döner. Her yeni oturum/iptal `_gen` kuşak sayacını
    artırır: eski kuşağa ait geç sonuçlar yok sayılır. Durum dışı kayıt çağrıları (ör. kayıt
    yokken `stop_recording`) yok sayılır; dosya/yeniden deneme ise `error` yayınlar. Hatalar
    `error` ile Türkçe mesaj olarak yayınlanır; başarısız mikrofon kaydının sesi (ayar
    açıksa) yeniden denemek için saklanır.
    """

    state_changed = Signal(object)
    session_updated = Signal(object)
    error = Signal(str)
    level_changed = Signal(float)
    buckets_changed = Signal(object)
    ready_changed = Signal(bool)
    cancelled = Signal()
    result_ready = Signal(str)
    edit_learned = Signal(object)
    partial_text = Signal(str)
    warning = Signal(str)  # kaydı durdurmayan uyarılar (ör. mikrofondan ses gelmiyor)
    failed_audio_changed = Signal(bool)  # yeniden denenebilir kayıt var/yok
    undo_requested = Signal()  # dikte yalnızca "geri al"dı: yapıştırma yerine geri alma

    def __init__(
        self,
        settings: Settings,
        *,
        recorder,
        stt: SttEngine,
        llm: LlmProvider,
        pool: QThreadPool | None = None,
        audio_loader: Callable[[str], np.ndarray] | None = None,
        failed_audio_path: Path | None = None,
        parent=None,
    ):
        """`failed_audio_path`: başarısız diktenin sesinin saklanacağı WAV yolu
        (`paths.failed_audio_path()`); None ise saklama/yeniden deneme kapalıdır."""
        super().__init__(parent)
        self._settings = settings
        self._recorder, self._stt, self._llm = recorder, stt, llm
        self._audio_loader = audio_loader or _default_audio_loader
        self._pool = pool or QThreadPool.globalInstance()
        self._state = DictationState.IDLE
        self._session = Session()
        self._failed_audio_path = failed_audio_path
        self._jobs: set = set()  # teslim edilene kadar canlı tutulan sinyal nesneleri
        self._gen = 0  # iptal sonrası gelen sonuçları ayırt etmek için
        self._active_profile: AppProfile | None = None
        self._source = "mic"  # "mic" | "file" | "retry": başarısızlıkta ses saklanır mı
        self._chunk_mode = False  # kayıt başında sabitlenir; kayıt ortası ayar değiştirmez
        self._chunk_seq = 0
        self._chunk_texts: dict[int, str] = {}
        self._chunk_queue: deque[np.ndarray] = deque()
        self._chunk_running = False  # parçalar sırayla, birer birer çözümlenir
        self._chunks_received = 0
        self._chunks_expected: int | None = None  # stop() anında kayıtçının kestiği sayı
        self._pending_tail: np.ndarray | None = None  # geç parçalar gelince kuyruğa girer
        self._chunk_sample_total = 0
        self._recording_stopped = False
        self._session_audio: list[np.ndarray] = []  # başarısızlıkta saklamak için
        # Hata oldu ama kayıtçının kestiği bazı parçaların sinyali henüz gelmedi: sesi eksiksiz
        # saklamak için onlar (en çok LATE_CHUNK_TIMEOUT_MS) beklenir. (mesaj, kuyruk, beklenen)
        self._failure: tuple[str, np.ndarray | None, int] | None = None
        self._compiled_dictionary_rules: list = []
        recorder.level_changed.connect(self.level_changed)
        recorder.buckets_changed.connect(self.buckets_changed)
        recorder.error.connect(self._on_recorder_error)
        recorder.limit_reached.connect(self._on_limit_reached)
        recorder.silence_reached.connect(self._on_silence)
        recorder.chunk_ready.connect(self._on_chunk)
        recorder_warning = getattr(recorder, "warning", None)
        if recorder_warning is not None:
            recorder_warning.connect(self.warning)
        self._push_dictionary()
        self._recorder.set_chunking(settings.stt.live_chunk_s, settings.stt.live_max_chunk_s)

    # ---- özellikler
    @property
    def state(self) -> DictationState:
        return self._state

    @property
    def session(self) -> Session:
        return self._session

    @property
    def has_failed_audio(self) -> bool:
        """Yeniden denenebilecek, saklanmış başarısız bir kayıt var mı?"""
        return self._failed_audio_path is not None and self._failed_audio_path.exists()

    def update_settings(self, settings: Settings) -> None:
        """Yeni ayarları uygular; sözlük hemen STT motoruna iletilir. Motor ve LLM
        sağlayıcısı burada değişmez (bkz. `set_llm`)."""
        self._settings = settings
        self._push_dictionary()
        # Süren kayıtta parçalama değişmez (parçalar yarıda farklı yola girip kaybolmasın);
        # yeni değerler bir sonraki _start_recording'de uygulanır.
        if self._state is not DictationState.RECORDING:
            self._apply_chunking()

    def set_llm(self, llm: LlmProvider) -> None:
        """Ayar değişince sağlayıcıyı yeniden başlatmadan değiştirir."""
        self._llm = llm

    @property
    def llm_enabled(self) -> bool:
        return self._settings.llm.enabled

    @property
    def active_profile(self) -> AppProfile | None:
        """O anki oturumu başlatan tetikleyicide eşleşen profil (varsa). `app.py` sonucu
        teslim ederken bunu okumalı — ambient/son-kısayol durumu değil, bu belirli
        oturuma ait gerçek profili verir (tepsi/pencere/IPC ile başlatılan diktelerde de
        doğru sonucu verir; app.ctx.active_profile yalnızca son global kısayolu izler)."""
        return self._active_profile

    # ---- kamu slotları
    @Slot()
    def warm_up(self) -> None:
        """STT modelini arka planda yükler; bitince `ready_changed(True)`, hata olursa
        `error("STT modeli yüklenemedi: …")`. Ardından LLM ön ısıtmasını da tetikler."""
        # Isınma iptal kuşağının dışındadır: kullanıcı iptali modeli yüklemeyi bozmamalı.
        self._run(
            self._stt.warm_up,
            lambda _: self.ready_changed.emit(True),
            lambda e: self.error.emit(f"STT modeli yüklenemedi: {e}"),
        )
        self.prewarm_llm()

    @Slot()
    def prewarm_llm(self) -> None:
        """LLM sağlayıcıyı (destekliyorsa) arka planda ısındırır; sonucu beklenmez."""
        warm = getattr(self._llm, "warm_up", None)
        if not (self._settings.llm.enabled and self._settings.llm.prewarm and warm is not None):
            return
        self._run(
            warm,
            lambda _: None,
            lambda e: log.warning("LLM ısındırma başarısız: %s", e),
        )

    @Slot()
    def cancel(self) -> None:
        """Kaydı ya da süren çözümleme/düzeltmeyi iptal eder; IDLE/RESULT'ta hiçbir şey yapmaz.

        Kayıttaki ses atılır (saklanmaz), oturum boşaltılır, `cancelled` yayınlanır."""
        if self._state in (DictationState.IDLE, DictationState.RESULT):
            return
        self._gen += 1  # bu kuşaktan önceki işlerin sonuçları yok sayılacak
        if self._state is DictationState.RECORDING:
            self._recorder.stop()  # ses atılır
        self._reset_chunks()
        self._session = Session()
        self.session_updated.emit(self._session)
        self._set_state(DictationState.IDLE)
        self.cancelled.emit()

    @Slot()
    @Slot(str)
    def toggle(self, mode: str = "correct", *, profile: AppProfile | None = None) -> None:
        """IDLE/RESULT'ta kaydı başlatır, kayıttayken durdurur; çözümleme sürerken yok sayılır."""
        if self._state in (DictationState.IDLE, DictationState.RESULT):
            self.start_recording(mode, profile=profile)
        elif self._state is DictationState.RECORDING:
            self.stop_recording()
        else:
            log.debug("toggle yok sayıldı (durum: %s)", self._state)

    @Slot()
    @Slot(str)
    def start_recording(self, mode: str = "correct", *, profile: AppProfile | None = None) -> None:
        """Kaydı başlatır (bas-konuş basışı, IPC `--start`); yalnızca IDLE/RESULT'ta.

        `profile` verilirse ve `mode` "correct" ise profilin modu kullanılır. Mikrofon
        açılamazsa `error` yayınlanır ve durum değişmez."""
        if self._state in (DictationState.IDLE, DictationState.RESULT):
            self._start_recording(mode, profile=profile)
        else:
            log.debug("start_recording yok sayıldı (durum: %s)", self._state)

    @Slot()
    def stop_recording(self) -> None:
        """Kaydı durdurup çözümlemeyi başlatır (bas-konuş bırakma, IPC `--stop`)."""
        if self._state is DictationState.RECORDING:
            self._stop_and_transcribe()
        else:
            log.debug("stop_recording yok sayıldı (durum: %s)", self._state)

    @Slot(str)
    def transcribe_file(self, path: str) -> None:
        """Bir ses dosyasını mikrofon kaydı yerine kaynak olarak çözümler.

        Hata olursa ses saklanmaz; sonuç otomatik yapıştırılmaz, yalnızca panoya kopyalanır
        (bkz. `app._on_result_ready`)."""
        if self._state not in (DictationState.IDLE, DictationState.RESULT):
            self.error.emit("Önce süren işi bitirin.")
            return
        self._gen += 1  # eski çeviri/prompt gibi bekleyen işler bu oturuma yazılmasın
        self._active_profile = None
        self._source = "file"
        self._begin_session(Session(source_path=path), DictationState.TRANSCRIBING)
        lang = self._settings.stt.language
        self._spawn(
            lambda: self._stt.transcribe(self._audio_loader(path), lang),
            self._on_transcribed,
            self._on_file_transcribe_error,
        )

    @Slot()
    def retry_last_failed(self) -> bool:
        """Saklanmış başarısız kaydı yeniden çözümler (ardından normal LLM/teslim akışı).
        Oturum sonuca ulaşınca (RESULT) dosya silinir (`failed_audio_changed(False)`);
        yeniden deneme başarısız olur ya da iptal edilirse dosya korunur. Başlatılamazsa `error`
        yayınlanır ve False döner."""
        if self._state not in (DictationState.IDLE, DictationState.RESULT):
            self.error.emit("Önce süren işi bitirin.")
            return False
        path = self._failed_audio_path
        if path is None or not path.exists():
            self.error.emit("Yeniden denenecek kayıt yok.")
            return False
        from dikte.audio.wav import load_wav

        self._gen += 1
        self._active_profile = None
        self._source = "retry"
        self._reset_chunks()
        self._begin_session(Session(), DictationState.TRANSCRIBING)
        lang = self._settings.stt.language
        self._spawn(
            lambda: self._stt.transcribe(load_wav(path), lang),
            self._on_transcribed,
            self._on_stt_error,
        )
        return True

    def _on_file_transcribe_error(self, msg: str) -> None:
        self.error.emit(f"Dosya çözümlenemedi: {msg}")
        self._set_state(DictationState.IDLE)

    @Slot(str)
    def request_translation(self, text: str) -> None:
        """Sonuç ekranından elle istenen çeviri; sonuç `session_updated` ile gelir.
        Yalnızca RESULT'ta çalışır; yanıt geldiğinde oturum değişmişse sonuç atılır."""
        if not self._result_request_allowed("request_translation"):
            return
        self._spawn_for_session(
            lambda: tasks.translate(self._llm, text),
            "translation",
            lambda e: self.error.emit(f"Çeviri başarısız: {e}"),
        )

    @Slot(str)
    def request_enhanced_prompt(self, text: str) -> None:
        """Sonuç ekranından elle istenen prompt iyileştirme; sonuç `session_updated` ile gelir.
        Yalnızca RESULT'ta çalışır; yanıt geldiğinde oturum değişmişse sonuç atılır."""
        if not self._result_request_allowed("request_enhanced_prompt"):
            return
        self._spawn_for_session(
            lambda: tasks.enhance_prompt(self._llm, text),
            "enhanced_prompt",
            lambda e: self.error.emit(f"Prompt oluşturma başarısız: {e}"),
        )

    def _result_request_allowed(self, name: str) -> bool:
        if self._state is not DictationState.RESULT:
            log.debug("%s yok sayıldı (durum: %s)", name, self._state)
            return False
        return self._require_llm()

    def _spawn_for_session(self, fn, field_name: str, on_error) -> None:
        """İsteği başlatan oturumun kimliğini yakalar; sonuç geldiğinde hâlâ aynı oturumun
        sonuç ekranındaysak alana yazar, değilse (yeni dikte, iptal) sonucu atar."""
        session_id = self._session.id

        def on_result(out) -> None:
            if self._state is not DictationState.RESULT or self._session.id != session_id:
                log.debug("başka oturuma ait %s sonucu yok sayıldı", field_name)
                return
            self._update_session(**{field_name: out})

        self._spawn(fn, on_result, on_error)

    @Slot(str)
    def apply_edit(self, text: str) -> None:
        """Kullanıcının sonuç penceresinde elle yaptığı düzenlemeyi oturuma yazar;
        RESULT dışında yok sayılır. Öğrenilebilir değişiklikler edit_learned ile bildirilir."""
        if self._state is not DictationState.RESULT:
            return
        before = self._session.corrected_text
        # changes=(): LLM düzeltmesinin ham metne göre vurguları artık geçersiz — kullanıcının
        # düzenlediği yeni metinde eski ofsetler yanlış kelimeleri işaretlerdi.
        self._update_session(corrected_text=text, changes=())
        changes = word_changes(before, text)
        if changes:
            self.edit_learned.emit(changes)

    # ---- iç akış
    def _push_dictionary(self) -> None:
        entries = self._settings.dictionary.entries
        self._compiled_dictionary_rules = compile_rules(entries)
        setter = getattr(self._stt, "set_dictionary", None)
        if setter is None:
            return
        setter(hotwords(entries), prompt_terms(entries))

    def _require_llm(self) -> bool:
        if self._settings.llm.enabled:
            return True
        self.error.emit("LLM kapalı; Ayarlar'dan metin düzeltmeyi açın.")
        return False

    def _apply_chunking(self) -> None:
        stt = self._settings.stt
        self._recorder.set_chunking(stt.live_chunk_s, stt.live_max_chunk_s)

    def _reset_chunks(self) -> None:
        self._chunk_seq = 0
        self._chunk_texts = {}
        self._chunk_queue.clear()
        self._chunk_running = False
        self._chunks_received = 0
        self._chunks_expected = None
        self._pending_tail = None
        self._chunk_sample_total = 0
        self._recording_stopped = False
        self._session_audio = []
        self._failure = None

    def _begin_session(self, session: Session, state: DictationState) -> None:
        """Yeni oturuma geçer: önce oturum ve durum değişir, `session_updated` EN SON
        yayınlanır. RESULT durumundayken boş oturum yayınlanırsa geçmiş senkronu
        (`app._sync_history_on_edit`) onu önceki sonucun yerine boş satır olarak yazardı."""
        self._session = session
        self._set_state(state)
        self.session_updated.emit(self._session)

    def _start_recording(self, mode: str = "correct", *, profile: AppProfile | None = None) -> None:
        # Parçalama kipi bu kayıt boyunca sabittir (kayıt ortası update_settings değiştirmez).
        self._apply_chunking()
        self._recorder.start()
        if not self._recorder.is_recording:
            # AudioRecorder.start() mikrofon açılamazsa hatayı zaten error sinyaliyle
            # bildirdi (_on_recorder_error tetiklendi). Önceki oturum/durum (ör. RESULT
            # ekranındaki sonuç) olduğu gibi kalır; hiç ses yakalanmayan bir kayıt
            # kullanıcıya "kayıtta" gösterilmez.
            return
        self._gen += 1  # eski çeviri/prompt gibi bekleyen işler bu oturuma yazılmasın
        self._active_profile = profile
        self._source = "mic"
        self._reset_chunks()
        self._chunk_mode = self._settings.stt.live_chunk_s > 0
        effective_mode = profile.mode if profile and mode == "correct" else mode
        self._begin_session(
            Session(mode=effective_mode, profile=profile.name if profile else ""),
            DictationState.RECORDING,
        )

    def _stop_and_transcribe(self) -> None:
        audio: np.ndarray = self._recorder.stop()
        self._set_state(DictationState.TRANSCRIBING)
        lang = self._settings.stt.language
        if not self._chunk_mode:
            # Beklenmedik biçimde gelmiş parçalar varsa (kayıtçı parçalıyorsa) başa eklenir.
            full = np.concatenate([*self._session_audio, audio]) if self._session_audio else audio
            self._session_audio = [full]
            self._spawn(
                lambda: self._stt.transcribe(full, lang),
                self._on_transcribed,
                self._on_stt_error,
            )
            return
        self._recording_stopped = True
        emitted = getattr(self._recorder, "chunks_emitted", None)
        expected = self._chunks_received
        if isinstance(emitted, int) and emitted > expected:
            expected = emitted
        self._chunks_expected = expected
        self._pending_tail = audio if audio.size else None
        if self._chunks_received < expected:
            # Kayıtçı durdurmadan hemen önce (çoğu zaman tuşa basmadan önceki sessizlikte)
            # parça kesti; kuyruklu sinyali henüz gelmedi. Onu bekle, kuyruğu sonra ekle.
            log.debug("%d geç parça bekleniyor", expected - self._chunks_received)
            gen = self._gen
            QTimer.singleShot(LATE_CHUNK_TIMEOUT_MS, self, lambda: self._on_late_timeout(gen))
        self._release_tail_if_ready()
        self._maybe_finish_transcription()

    def _on_chunk(self, audio: np.ndarray) -> None:
        if self._failure is not None and self._state is DictationState.TRANSCRIBING:
            # Hata sonrası geç gelen parça: çözümlenmez, yalnızca saklanacak sese sırayla eklenir.
            self._chunks_received += 1
            self._session_audio.append(audio)
            if self._chunks_received >= self._failure[2]:
                self._finish_failure(self._gen)
            return
        if self._state is DictationState.RECORDING:
            self._chunks_received += 1
            if self._chunk_mode:
                self._enqueue_chunk(audio)
            else:
                # Parçalama bu kayıtta kapalıyken gelen parça: sesi kaybetme, sona ekle.
                self._session_audio.append(audio)
            return
        if (
            self._state is DictationState.TRANSCRIBING
            and self._recording_stopped
            and self._chunks_expected is not None
            and self._chunks_received < self._chunks_expected
        ):
            # Durdurmadan önce kesilmiş, sinyali geç gelmiş parça: aynı oturuma aittir.
            self._chunks_received += 1
            self._enqueue_chunk(audio)
            self._release_tail_if_ready()
            return
        log.debug("oturum dışı parça yok sayıldı (durum: %s)", self._state)

    def _on_late_timeout(self, gen: int) -> None:
        if gen != self._gen or self._state is not DictationState.TRANSCRIBING:
            return
        if self._chunks_expected is None or self._chunks_received >= self._chunks_expected:
            return
        log.warning(
            "%d geç parça %d ms içinde gelmedi; eldeki sesle devam ediliyor",
            self._chunks_expected - self._chunks_received,
            LATE_CHUNK_TIMEOUT_MS,
        )
        self._chunks_expected = self._chunks_received
        self._release_tail_if_ready()
        self._maybe_finish_transcription()

    def _release_tail_if_ready(self) -> None:
        if self._chunks_expected is None or self._chunks_received < self._chunks_expected:
            return
        if self._pending_tail is not None:
            tail, self._pending_tail = self._pending_tail, None
            self._enqueue_chunk(tail)

    def _enqueue_chunk(self, audio: np.ndarray) -> None:
        self._session_audio.append(audio)
        self._chunk_sample_total += audio.shape[0]
        self._chunk_queue.append(audio)
        self._pump_chunks()

    def _pump_chunks(self) -> None:
        """Sıradaki parçayı, öncekisi bittiyse başlatır. Parçalar sırayla çözümlenir ve
        bağlam (önceki metin) GUI iş parçacığında, gönderim anında hesaplanır."""
        if self._chunk_running or not self._chunk_queue:
            return
        audio = self._chunk_queue.popleft()
        self._chunk_running = True
        seq = self._chunk_seq
        self._chunk_seq += 1
        lang = self._settings.stt.language
        previous = self._joined_text()
        self._spawn(
            lambda: self._stt.transcribe(audio, lang, previous_text=previous, allow_empty=True),
            lambda result: self._on_chunk_transcribed(seq, result),
            self._on_chunk_error,
        )

    def _on_chunk_transcribed(self, seq: int, result: TranscriptResult) -> None:
        self._chunk_texts[seq] = result.text
        self._chunk_running = False
        self.partial_text.emit(self._joined_text())
        self._pump_chunks()
        self._maybe_finish_transcription()

    def _on_chunk_error(self, msg: str) -> None:
        self._fail_after_drain(self._stt_error_message(msg))

    def _fail_after_drain(self, message: str) -> None:
        """Canlı kayıtta hata: mikrofonu kapatır, kayıtçının kestiği ama sinyali henüz
        gelmemiş parçaları bekler ve sesi doğru sırayla (parçalar, geç parçalar, kuyruk)
        saklayarak başarısız olur."""
        self._gen += 1  # bekleyen diğer parçaların geç gelen sonuçları da yok sayılsın
        self._chunk_running = False
        # Kuyrukta bekleyen (henüz çözümlenmemiş) parçaların sesi zaten _session_audio'da.
        self._chunk_queue.clear()
        tail = self._pending_tail
        if self._state is DictationState.RECORDING:
            tail = self._recorder.stop()  # mikrofon açık kalmasın; ses saklanabilir
            self._set_state(DictationState.TRANSCRIBING)
        self._pending_tail = None
        self._recording_stopped = False
        emitted = getattr(self._recorder, "chunks_emitted", None)
        expected = max(self._chunks_received, emitted if isinstance(emitted, int) else 0)
        kept_tail = tail if tail is not None and tail.size else None
        self._failure = (message, kept_tail, expected)
        gen = self._gen
        if self._chunks_received < expected:
            QTimer.singleShot(LATE_CHUNK_TIMEOUT_MS, self, lambda: self._finish_failure(gen))
            return
        self._finish_failure(gen)

    def _finish_failure(self, gen: int) -> None:
        if gen != self._gen or self._failure is None:
            return
        message, tail, _expected = self._failure
        self._failure = None
        if tail is not None:
            self._session_audio.append(tail)
        self._fail(message, keep_audio=NO_SPEECH_MESSAGE not in message)

    def _maybe_finish_transcription(self) -> None:
        if not self._recording_stopped or self._state is not DictationState.TRANSCRIBING:
            return
        if self._chunk_running or self._chunk_queue or self._pending_tail is not None:
            return
        if self._chunks_expected is not None and self._chunks_received < self._chunks_expected:
            return
        self._recording_stopped = False  # tek sefer bitir
        self._on_transcribed(
            TranscriptResult(
                text=self._joined_text(),
                language=self._settings.stt.language,
                duration_s=self._chunk_sample_total / self._settings.audio.sample_rate,
                segments=(),
            )
        )

    def _joined_text(self) -> str:
        pieces = (self._chunk_texts[i].strip() for i in sorted(self._chunk_texts))
        return " ".join(p for p in pieces if p)

    def _on_transcribed(self, result: TranscriptResult) -> None:
        if not result.text.strip():
            # Sessiz/yanlışlıkla başlatılmış kayıt: saklanacak değerli ses yok; daha önce
            # saklanmış gerçek bir başarısız kaydın üzerine de yazılmamalı.
            self._fail("Konuşma algılanamadı, ses boş görünüyor.", keep_audio=False)
            return
        self._session_audio = []
        if self._settings.voice_commands and is_undo_command(result.text):
            self.undo_requested.emit()
            self._set_state(DictationState.IDLE)
            return
        entries = self._settings.dictionary.entries
        text = apply_compiled(result.text, self._compiled_dictionary_rules)
        if self._settings.voice_commands:
            text = apply_commands(text)
        self._update_session(raw_text=text, duration_s=result.duration_s)
        profile_skips_llm = (
            self._active_profile is not None and not self._active_profile.llm_enabled
        )
        if not self._settings.llm.enabled or profile_skips_llm:  # LLM kapalı: ham metin sonuç
            self._update_session(corrected_text=text)
            self._after_correction()
            return
        self._set_state(DictationState.CORRECTING)
        raw = text
        glossary = prompts.glossary_block(
            [e.term for e in entries], self._settings.dictionary.user_instructions
        )
        self._spawn(
            lambda: tasks.correct(
                self._llm, raw, glossary=glossary, sanity_check=self._settings.llm.sanity_check
            ),
            self._on_corrected,
            self._on_llm_error,
        )

    def _on_corrected(self, res: tasks.CorrectionResult) -> None:
        self._update_session(
            corrected_text=res.corrected_text or self._session.raw_text, changes=res.changes
        )
        self._after_correction()

    def _after_correction(self) -> None:
        """Düzeltme (veya LLM-kapalı kısayolu) bittikten sonra moda göre devam eder:
        correct ise doğrudan sonuç, translate/prompt ise düzeltilmiş metin üzerinden
        ikinci bir LLM çağrısı yapılır."""
        mode = self._session.mode
        if mode == "correct":
            self._finish_result()
            return
        # profile_skips_llm: _on_transcribed'daki düzeltme-atlama kontrolüyle aynı — profil
        # llm_enabled=False dediyse (ör. hassas bir uygulama eşleşti), çeviri/prompt da uzak
        # sağlayıcıya gitmemeli. Yalnızca global ayarı kontrol etmek bu korumayı atlıyordu.
        profile_skips_llm = (
            self._active_profile is not None and not self._active_profile.llm_enabled
        )
        if not self._settings.llm.enabled or profile_skips_llm:
            self.error.emit(
                "LLM kapalı; çeviri/prompt için Ayarlar'dan açın. Düzeltilmemiş metin yapıştırıldı."
            )
            self._finish_result()
            return
        corrected = self._session.corrected_text
        if mode == "translate":
            self._spawn(
                lambda: tasks.translate(self._llm, corrected),
                self._on_translated,
                self._on_mode_error,
            )
        else:  # "prompt"
            self._spawn(
                lambda: tasks.enhance_prompt(self._llm, corrected),
                self._on_prompted,
                self._on_mode_error,
            )

    def _on_translated(self, text: str) -> None:
        self._update_session(translation=text)
        self._finish_result()

    def _on_prompted(self, text: str) -> None:
        self._update_session(enhanced_prompt=text)
        self._finish_result()

    def _on_mode_error(self, msg: str) -> None:
        self.error.emit(f"Çeviri/prompt başarısız, düzeltilmiş metin gösteriliyor: {msg}")
        self._finish_result()

    def _on_llm_error(self, msg: str) -> None:
        self.error.emit(f"LLM düzeltmesi başarısız, ham metin gösteriliyor: {msg}")
        self._update_session(corrected_text=self._session.raw_text)
        self._finish_result()

    def _finish_result(self) -> None:
        """RESULT durumuna geçer, ardından metni teslim için yayınlar (sıra önemlidir:
        geçmişe yazma ve pencere güncellemesi yapıştırmadan önce tamamlanmalı).

        Yeniden denenen kaydın dosyası ancak burada, oturum başarıyla bittiğinde silinir:
        LLM/teslim sırasında iptal edilirse kayıt kaybolmaz."""
        if self._source == "retry":
            self._discard_failed_audio()
        self._set_state(DictationState.RESULT)
        self.result_ready.emit(self._session.output_text)

    @staticmethod
    def _stt_error_message(msg: str) -> str:
        return f"Transkripsiyon başarısız: {msg}"

    def _on_stt_error(self, msg: str) -> None:
        self._fail(self._stt_error_message(msg), keep_audio=NO_SPEECH_MESSAGE not in msg)

    def _fail(self, message: str, *, keep_audio: bool = True) -> None:
        """Çözümleme başarısız/boş: gerekirse sesi saklar, ipucuyla hata yayınlar, IDLE'a döner."""
        if keep_audio:
            message += self._keep_failed_audio()
        else:
            self._session_audio = []
            if self._source == "retry" and self.has_failed_audio:
                message += RETRY_HINT
        self.error.emit(message)
        self._set_state(DictationState.IDLE)

    def _keep_failed_audio(self) -> str:
        """Mikrofon kaydını WAV olarak saklar; hata mesajına eklenecek ipucunu döndürür."""
        audio_parts, self._session_audio = self._session_audio, []
        if self._source == "retry":
            return RETRY_HINT if self.has_failed_audio else ""
        path = self._failed_audio_path
        if self._source != "mic" or path is None or not self._settings.keep_failed_audio:
            return ""
        audio = np.concatenate(audio_parts) if audio_parts else np.zeros(0, dtype=np.float32)
        if audio.size == 0:
            return ""
        from dikte.audio.wav import save_wav

        try:
            save_wav(path, audio, self._settings.audio.sample_rate)
        except OSError as exc:
            log.exception("başarısız diktenin sesi saklanamadı: %s", path)
            return f" Ses kaydı saklanamadı ({exc}); diskte yer olduğunu kontrol edin."
        log.info("başarısız diktenin sesi saklandı: %s", path)
        self.failed_audio_changed.emit(True)
        return RETRY_HINT

    def _discard_failed_audio(self) -> None:
        path = self._failed_audio_path
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.exception("yeniden denenen kayıt silinemedi: %s", path)
            return
        self.failed_audio_changed.emit(False)

    def _on_limit_reached(self) -> None:
        if self._state is DictationState.RECORDING:
            log.info("kayıt süresi sınırına ulaşıldı, otomatik durduruluyor")
            self._stop_and_transcribe()

    def _on_silence(self) -> None:
        if self._state is DictationState.RECORDING:
            log.info("sessizlik: kayıt otomatik durduruldu")
            self._stop_and_transcribe()

    def _on_recorder_error(self, msg: str) -> None:
        if self._state is not DictationState.RECORDING:
            if msg == DEVICE_LOST_MESSAGE:
                # Akış kullanıcı durdurduktan sonra bitti bildirimi: kayıt zaten tamam.
                log.debug("kayıt bittikten sonra gelen cihaz bildirimi yok sayıldı")
                return
            self.error.emit(msg)
            return
        # Kayıt sürerken cihaz kaybı vb.: akışı kapat (tutamaç sızmasın, sonraki start()
        # çalışsın), bekleyen parça sonuçlarını geçersiz kıl, geç parçaları bekleyip sesi sakla.
        self._fail_after_drain(msg)

    def _set_state(self, new: DictationState) -> None:
        if new is self._state:
            return
        self._state = new
        self.state_changed.emit(new)

    def _update_session(self, **kwargs) -> None:
        self._session = self._session.with_(**kwargs)
        self.session_updated.emit(self._session)

    def _spawn(self, fn, on_result, on_error) -> None:
        """İşi havuzda çalıştırır; iptal edilmiş kuşağın sonuçları yok sayılır."""
        gen = self._gen

        def guarded_result(result) -> None:
            if gen == self._gen:
                on_result(result)
            else:
                log.debug("iptal edilmiş işin sonucu yok sayıldı")

        def guarded_error(message: str) -> None:
            if gen == self._gen:
                on_error(message)
            else:
                log.debug("iptal edilmiş işin hatası yok sayıldı: %s", message)

        self._run(fn, guarded_result, guarded_error)

    def _run(self, fn, on_result, on_error) -> None:
        """run_in_pool + sinyal nesnesini sonucu teslim edilene kadar canlı tutma
        (run_in_pool sözleşmesi). Bırakma geri çağrılardan sonra ve olay döngüsüne
        ertelenerek yapılır: nesne kendi sinyalinin teslimatı sırasında yok edilmesin."""
        holder: list = []

        def release() -> None:
            if holder:
                signals = holder[0]
                QTimer.singleShot(0, self, lambda: self._jobs.discard(signals))

        signals = run_in_pool(fn, on_result, on_error, self._pool, on_finished=release)
        holder.append(signals)
        self._jobs.add(signals)
