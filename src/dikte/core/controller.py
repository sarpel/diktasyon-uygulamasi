from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from dikte.config import Settings
from dikte.core.state import DictationState, Session
from dikte.core.workers import run_in_pool
from dikte.llm import tasks
from dikte.llm.provider import LlmProvider
from dikte.stt.engine import SttEngine
from dikte.stt.result import TranscriptResult

log = logging.getLogger(__name__)


class DictationController(QObject):
    state_changed = Signal(object)
    session_updated = Signal(object)
    error = Signal(str)
    level_changed = Signal(float)
    buckets_changed = Signal(object)
    ready_changed = Signal(bool)

    def __init__(
        self,
        settings: Settings,
        *,
        recorder,
        stt: SttEngine,
        llm: LlmProvider,
        pool: QThreadPool | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._recorder, self._stt, self._llm = recorder, stt, llm
        self._pool = pool or QThreadPool.globalInstance()
        self._state = DictationState.IDLE
        self._session = Session()
        self._jobs: list = []  # canlı sinyal nesneleri
        recorder.level_changed.connect(self.level_changed)
        recorder.buckets_changed.connect(self.buckets_changed)
        recorder.error.connect(self._on_recorder_error)
        recorder.limit_reached.connect(self._on_limit_reached)

    # ---- özellikler
    @property
    def state(self) -> DictationState:
        return self._state

    @property
    def session(self) -> Session:
        return self._session

    def update_settings(self, settings: Settings) -> None:
        self._settings = settings

    def set_llm(self, llm: LlmProvider) -> None:
        """Ayar değişince sağlayıcıyı yeniden başlatmadan değiştirir."""
        self._llm = llm

    @property
    def llm_enabled(self) -> bool:
        return self._settings.llm.enabled

    # ---- kamu slotları
    @Slot()
    def warm_up(self) -> None:
        self._spawn(
            self._stt.load,
            lambda _: self.ready_changed.emit(True),
            lambda e: self.error.emit(f"STT modeli yüklenemedi: {e}"),
        )

    @Slot()
    def toggle(self) -> None:
        if self._state in (DictationState.IDLE, DictationState.RESULT):
            self._start_recording()
        elif self._state is DictationState.RECORDING:
            self._stop_and_transcribe()
        else:
            log.debug("toggle yok sayıldı (durum: %s)", self._state)

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

    # ---- iç akış
    def _require_llm(self) -> bool:
        if self._settings.llm.enabled:
            return True
        self.error.emit("LLM kapalı; Ayarlar'dan metin düzeltmeyi açın.")
        return False

    def _start_recording(self) -> None:
        self._session = Session()
        self.session_updated.emit(self._session)
        self._recorder.start()
        self._set_state(DictationState.RECORDING)

    def _stop_and_transcribe(self) -> None:
        audio: np.ndarray = self._recorder.stop()
        self._set_state(DictationState.TRANSCRIBING)
        self._spawn(
            lambda: self._stt.transcribe(audio, self._settings.stt.language),
            self._on_transcribed,
            self._on_stt_error,
        )

    def _on_transcribed(self, result: TranscriptResult) -> None:
        if not result.text.strip():
            self.error.emit("Konuşma algılanamadı, ses boş görünüyor.")
            self._set_state(DictationState.IDLE)
            return
        self._update_session(raw_text=result.text, duration_s=result.duration_s)
        if not self._settings.llm.enabled:  # LLM kapalı: ham metin sonuç olarak gösterilir
            self._update_session(corrected_text=result.text)
            self._set_state(DictationState.RESULT)
            return
        self._set_state(DictationState.CORRECTING)
        raw = result.text
        self._spawn(lambda: tasks.correct(self._llm, raw), self._on_corrected, self._on_llm_error)

    def _on_corrected(self, res: tasks.CorrectionResult) -> None:
        self._update_session(
            corrected_text=res.corrected_text or self._session.raw_text, changes=res.changes
        )
        self._set_state(DictationState.RESULT)

    def _on_llm_error(self, msg: str) -> None:
        self.error.emit(f"LLM düzeltmesi başarısız, ham metin gösteriliyor: {msg}")
        self._update_session(corrected_text=self._session.raw_text)
        self._set_state(DictationState.RESULT)

    def _on_stt_error(self, msg: str) -> None:
        self.error.emit(f"Transkripsiyon başarısız: {msg}")
        self._set_state(DictationState.IDLE)

    def _on_limit_reached(self) -> None:
        if self._state is DictationState.RECORDING:
            log.info("kayıt süresi sınırına ulaşıldı, otomatik durduruluyor")
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
        sig = run_in_pool(fn, on_result, on_error, self._pool)
        self._jobs.append(sig)
        self._jobs = self._jobs[-16:]
