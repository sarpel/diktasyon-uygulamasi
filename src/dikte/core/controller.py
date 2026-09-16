from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np
from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from dikte.config import AppProfile, Settings
from dikte.core.state import DictationState, Session
from dikte.core.workers import run_in_pool
from dikte.llm import prompts, tasks
from dikte.llm.diff import word_changes
from dikte.llm.provider import LlmProvider
from dikte.stt.engine import SttEngine
from dikte.stt.result import TranscriptResult
from dikte.text.commands import apply_commands
from dikte.text.dictionary import apply_rules, hotwords, prompt_terms

log = logging.getLogger(__name__)


def _default_audio_loader(path: str) -> np.ndarray:
    from faster_whisper import decode_audio

    return decode_audio(path, sampling_rate=16000)


class DictationController(QObject):
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

    def __init__(
        self,
        settings: Settings,
        *,
        recorder,
        stt: SttEngine,
        llm: LlmProvider,
        pool: QThreadPool | None = None,
        audio_loader: Callable[[str], np.ndarray] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._recorder, self._stt, self._llm = recorder, stt, llm
        self._audio_loader = audio_loader or _default_audio_loader
        self._pool = pool or QThreadPool.globalInstance()
        self._state = DictationState.IDLE
        self._session = Session()
        self._jobs: list = []  # canlı sinyal nesneleri
        self._gen = 0  # iptal sonrası gelen sonuçları ayırt etmek için
        self._active_profile: AppProfile | None = None
        self._chunk_seq = 0
        self._chunk_texts: dict[int, str] = {}
        self._chunks_pending = 0
        self._chunk_sample_total = 0
        self._recording_stopped = False
        recorder.level_changed.connect(self.level_changed)
        recorder.buckets_changed.connect(self.buckets_changed)
        recorder.error.connect(self._on_recorder_error)
        recorder.limit_reached.connect(self._on_limit_reached)
        recorder.silence_reached.connect(self._on_silence)
        recorder.chunk_ready.connect(self._on_chunk)
        self._push_dictionary()
        self._recorder.set_chunking(settings.stt.live_chunk_s, settings.stt.live_max_chunk_s)

    # ---- özellikler
    @property
    def state(self) -> DictationState:
        return self._state

    @property
    def session(self) -> Session:
        return self._session

    def update_settings(self, settings: Settings) -> None:
        self._settings = settings
        self._push_dictionary()
        self._recorder.set_chunking(settings.stt.live_chunk_s, settings.stt.live_max_chunk_s)

    def set_llm(self, llm: LlmProvider) -> None:
        """Ayar değişince sağlayıcıyı yeniden başlatmadan değiştirir."""
        self._llm = llm

    @property
    def llm_enabled(self) -> bool:
        return self._settings.llm.enabled

    # ---- kamu slotları
    @Slot()
    def warm_up(self) -> None:
        # Isınma iptal kuşağının dışındadır: kullanıcı iptali modeli yüklemeyi bozmamalı.
        self._track(
            run_in_pool(
                self._stt.warm_up,
                lambda _: self.ready_changed.emit(True),
                lambda e: self.error.emit(f"STT modeli yüklenemedi: {e}"),
                self._pool,
            )
        )
        self.prewarm_llm()

    @Slot()
    def prewarm_llm(self) -> None:
        """LLM sağlayıcıyı (destekliyorsa) arka planda ısındırır; sonucu beklenmez."""
        warm = getattr(self._llm, "warm_up", None)
        if not (self._settings.llm.enabled and self._settings.llm.prewarm and warm is not None):
            return
        self._track(
            run_in_pool(
                warm,
                lambda _: None,
                lambda e: log.warning("LLM ısındırma başarısız: %s", e),
                self._pool,
            )
        )

    @Slot()
    def cancel(self) -> None:
        """Kaydı ya da süren çözümleme/düzeltmeyi iptal eder; boşta ise hiçbir şey yapmaz."""
        if self._state in (DictationState.IDLE, DictationState.RESULT):
            return
        self._gen += 1  # bu kuşaktan önceki işlerin sonuçları yok sayılacak
        if self._state is DictationState.RECORDING:
            self._recorder.stop()  # ses atılır
        self._session = Session()
        self.session_updated.emit(self._session)
        self._set_state(DictationState.IDLE)
        self.cancelled.emit()

    @Slot()
    @Slot(str)
    def toggle(self, mode: str = "correct", *, profile: AppProfile | None = None) -> None:
        if self._state in (DictationState.IDLE, DictationState.RESULT):
            self.start_recording(mode, profile=profile)
        elif self._state is DictationState.RECORDING:
            self.stop_recording()
        else:
            log.debug("toggle yok sayıldı (durum: %s)", self._state)

    @Slot()
    @Slot(str)
    def start_recording(self, mode: str = "correct", *, profile: AppProfile | None = None) -> None:
        """Bas-konuş: tuş basılı tutulmaya başlayınca çağrılır."""
        if self._state in (DictationState.IDLE, DictationState.RESULT):
            self._start_recording(mode, profile=profile)
        else:
            log.debug("start_recording yok sayıldı (durum: %s)", self._state)

    @Slot()
    def stop_recording(self) -> None:
        """Bas-konuş: tuş bırakılınca çağrılır."""
        if self._state is DictationState.RECORDING:
            self._stop_and_transcribe()
        else:
            log.debug("stop_recording yok sayıldı (durum: %s)", self._state)

    @Slot(str)
    def transcribe_file(self, path: str) -> None:
        """Bir ses dosyasını mikrofon kaydı yerine kaynak olarak çözümler."""
        if self._state not in (DictationState.IDLE, DictationState.RESULT):
            self.error.emit("Önce süren işi bitirin.")
            return
        self._active_profile = None
        self._session = Session(source_path=path)
        self.session_updated.emit(self._session)
        self._set_state(DictationState.TRANSCRIBING)
        lang = self._settings.stt.language
        self._spawn(
            lambda: self._stt.transcribe(self._audio_loader(path), lang),
            self._on_transcribed,
            lambda e: self.error.emit(f"Dosya çözümlenemedi: {e}"),
        )

    @Slot(str)
    def request_translation(self, text: str) -> None:
        if not self._require_llm():
            return
        self._spawn(
            lambda: tasks.translate(self._llm, text),
            lambda out: self._update_session(translation=out),
            lambda e: self.error.emit(f"Çeviri başarısız: {e}"),
        )

    @Slot(str)
    def request_enhanced_prompt(self, text: str) -> None:
        if not self._require_llm():
            return
        self._spawn(
            lambda: tasks.enhance_prompt(self._llm, text),
            lambda out: self._update_session(enhanced_prompt=out),
            lambda e: self.error.emit(f"Prompt oluşturma başarısız: {e}"),
        )

    @Slot(str)
    def apply_edit(self, text: str) -> None:
        """Kullanıcının sonuç penceresinde elle yaptığı düzenlemeyi oturuma yazar;
        RESULT dışında yok sayılır. Öğrenilebilir değişiklikler edit_learned ile bildirilir."""
        if self._state is not DictationState.RESULT:
            return
        before = self._session.corrected_text
        self._update_session(corrected_text=text)
        changes = word_changes(before, text)
        if changes:
            self.edit_learned.emit(changes)

    # ---- iç akış
    def _push_dictionary(self) -> None:
        setter = getattr(self._stt, "set_dictionary", None)
        if setter is None:
            return
        entries = self._settings.dictionary.entries
        setter(hotwords(entries), prompt_terms(entries))

    def _require_llm(self) -> bool:
        if self._settings.llm.enabled:
            return True
        self.error.emit("LLM kapalı; Ayarlar'dan metin düzeltmeyi açın.")
        return False

    def _start_recording(self, mode: str = "correct", *, profile: AppProfile | None = None) -> None:
        self._active_profile = profile
        effective_mode = profile.mode if profile and mode == "correct" else mode
        self._session = Session(mode=effective_mode, profile=profile.name if profile else "")
        self.session_updated.emit(self._session)
        self._chunk_seq = 0
        self._chunk_texts = {}
        self._chunks_pending = 0
        self._chunk_sample_total = 0
        self._recording_stopped = False
        self._recorder.start()
        self._set_state(DictationState.RECORDING)

    def _stop_and_transcribe(self) -> None:
        audio: np.ndarray = self._recorder.stop()
        self._set_state(DictationState.TRANSCRIBING)
        if self._settings.stt.live_chunk_s <= 0:
            self._spawn(
                lambda: self._stt.transcribe(audio, self._settings.stt.language),
                self._on_transcribed,
                self._on_stt_error,
            )
            return
        self._recording_stopped = True
        if audio.size:
            self._spawn_chunk(audio)
        self._maybe_finish_transcription()

    def _on_chunk(self, audio: np.ndarray) -> None:
        if self._state is not DictationState.RECORDING:
            return
        self._spawn_chunk(audio)

    def _spawn_chunk(self, audio: np.ndarray) -> None:
        seq = self._chunk_seq
        self._chunk_seq += 1
        self._chunks_pending += 1
        self._chunk_sample_total += audio.shape[0]
        lang = self._settings.stt.language
        self._spawn(
            lambda: self._stt.transcribe(audio, lang, previous_text=self._joined_text()),
            lambda result: self._on_chunk_transcribed(seq, result),
            self._on_chunk_error,
        )

    def _on_chunk_transcribed(self, seq: int, result: TranscriptResult) -> None:
        self._chunk_texts[seq] = result.text
        self._chunks_pending -= 1
        self.partial_text.emit(self._joined_text())
        self._maybe_finish_transcription()

    def _on_chunk_error(self, msg: str) -> None:
        self._gen += 1  # bekleyen diğer parçaların geç gelen sonuçları da yok sayılsın
        self._on_stt_error(msg)

    def _maybe_finish_transcription(self) -> None:
        if self._chunks_pending != 0 or not self._recording_stopped:
            return
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
            self.error.emit("Konuşma algılanamadı, ses boş görünüyor.")
            self._set_state(DictationState.IDLE)
            return
        entries = self._settings.dictionary.entries
        text = apply_rules(result.text, entries)
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
            lambda: tasks.correct(self._llm, raw, glossary=glossary),
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
        if not self._settings.llm.enabled:
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
        geçmişe yazma ve pencere güncellemesi yapıştırmadan önce tamamlanmalı)."""
        self._set_state(DictationState.RESULT)
        self.result_ready.emit(self._session.output_text)

    def _on_stt_error(self, msg: str) -> None:
        self.error.emit(f"Transkripsiyon başarısız: {msg}")
        self._set_state(DictationState.IDLE)

    def _on_limit_reached(self) -> None:
        if self._state is DictationState.RECORDING:
            log.info("kayıt süresi sınırına ulaşıldı, otomatik durduruluyor")
            self._stop_and_transcribe()

    def _on_silence(self) -> None:
        if self._state is DictationState.RECORDING:
            log.info("sessizlik: kayıt otomatik durduruldu")
            self._stop_and_transcribe()

    def _on_recorder_error(self, msg: str) -> None:
        self.error.emit(msg)
        if self._state is DictationState.RECORDING:
            self._set_state(DictationState.IDLE)

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

        self._track(run_in_pool(fn, guarded_result, guarded_error, self._pool))

    def _track(self, signals) -> None:
        self._jobs.append(signals)
        self._jobs = self._jobs[-16:]
