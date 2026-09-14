import json
import threading

import numpy as np
import pytest
from PySide6.QtCore import QObject, QThreadPool, Signal

from dikte.config import Settings
from dikte.core.controller import DictationController
from dikte.core.state import DictationState
from dikte.stt.result import TranscriptResult


class FakeRecorder(QObject):
    level_changed = Signal(float)
    buckets_changed = Signal(object)
    limit_reached = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.started = self.stopped = False
        self.audio = np.ones(16000, dtype=np.float32) * 0.1

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
        return self.audio


class FakeStt:
    def __init__(self, text="merhaba dünya"):
        self.text, self.loaded = text, False

    @property
    def is_loaded(self):
        return self.loaded

    def load(self):
        self.loaded = True

    def transcribe(self, audio, language=None):
        return TranscriptResult(self.text, "tr", 1.0, ())


class FakeLlm:
    name = "fake"

    def __init__(self):
        self.calls = []

    def complete(self, system, user, *, json_schema=None, temperature=0.2):
        self.calls.append(user)
        if json_schema:
            return json.dumps({"corrected_text": "Merhaba dünya.", "changes": []})
        if "User request" in user:
            return "# Goal\nSay hello"
        return "Hello world."


@pytest.fixture
def ctl(qtbot):
    rec, stt, llm = FakeRecorder(), FakeStt(), FakeLlm()
    c = DictationController(Settings(), recorder=rec, stt=stt, llm=llm, pool=QThreadPool())
    return c, rec, stt, llm


def test_initial_state_idle(ctl):
    c, *_ = ctl
    assert c.state is DictationState.IDLE


def test_toggle_starts_recording(ctl, qtbot):
    c, rec, *_ = ctl
    with qtbot.waitSignal(c.state_changed):
        c.toggle()
    assert c.state is DictationState.RECORDING and rec.started


def test_full_cycle_reaches_result_with_texts(ctl, qtbot):
    c, rec, stt, llm = ctl
    c.toggle()
    with qtbot.waitSignal(
        c.state_changed,
        timeout=5000,
        check_params_cb=lambda s: s is DictationState.RESULT,
    ):
        c.toggle()
    assert rec.stopped
    assert c.session.raw_text == "merhaba dünya"
    assert c.session.corrected_text == "Merhaba dünya."


def test_toggle_ignored_while_transcribing(ctl, qtbot):
    c, *_ = ctl
    c.toggle()
    c.toggle()  # -> TRANSCRIBING (async)
    assert c.state is DictationState.TRANSCRIBING
    c.toggle()  # yok sayılmalı
    assert c.state is DictationState.TRANSCRIBING
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)


def test_toggle_from_result_starts_new_recording(ctl, qtbot):
    c, rec, *_ = ctl
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)
    c.toggle()
    assert c.state is DictationState.RECORDING and c.session.raw_text == ""


def test_llm_failure_still_shows_raw_text(qtbot):
    class BadLlm(FakeLlm):
        def complete(self, *a, **k):
            raise RuntimeError("down")

    rec, stt = FakeRecorder(), FakeStt()
    c = DictationController(Settings(), recorder=rec, stt=stt, llm=BadLlm(), pool=QThreadPool())
    errors = []
    c.error.connect(errors.append)
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)
    assert c.session.raw_text == "merhaba dünya"
    assert c.session.corrected_text == "merhaba dünya"  # düzeltme başarısızsa ham metin kopyalanır
    assert errors and "down" in errors[0]


def test_empty_transcript_goes_back_to_idle_with_error(qtbot):
    rec, stt = FakeRecorder(), FakeStt(text="")
    c = DictationController(Settings(), recorder=rec, stt=stt, llm=FakeLlm(), pool=QThreadPool())
    errors = []
    c.error.connect(errors.append)
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.IDLE, timeout=5000)
    assert errors


def test_request_translation_updates_session(ctl, qtbot):
    c, *_ = ctl
    with qtbot.waitSignal(
        c.session_updated, timeout=5000, check_params_cb=lambda s: s.translation != ""
    ):
        c.request_translation("Merhaba dünya.")
    assert c.session.translation == "Hello world."


def test_request_enhanced_prompt_updates_session(ctl, qtbot):
    c, *_ = ctl
    with qtbot.waitSignal(
        c.session_updated, timeout=5000, check_params_cb=lambda s: s.enhanced_prompt != ""
    ):
        c.request_enhanced_prompt("merhaba de")
    assert c.session.enhanced_prompt.startswith("# Goal")


def _disabled_llm_settings():
    from dikte.config import LlmSettings

    s = Settings()
    return s.model_copy(update={"llm": s.llm.model_copy(update={"enabled": False})}), LlmSettings


def test_llm_disabled_skips_correction(qtbot):
    settings, _ = _disabled_llm_settings()
    rec, stt, llm = FakeRecorder(), FakeStt(), FakeLlm()
    c = DictationController(settings, recorder=rec, stt=stt, llm=llm, pool=QThreadPool())
    states = []
    c.state_changed.connect(states.append)
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert DictationState.CORRECTING not in states
    assert c.session.corrected_text == "merhaba dünya"
    assert llm.calls == []  # LLM hiç çağrılmadı


def test_llm_disabled_rejects_translation(qtbot):
    settings, _ = _disabled_llm_settings()
    llm = FakeLlm()
    c = DictationController(
        settings, recorder=FakeRecorder(), stt=FakeStt(), llm=llm, pool=QThreadPool()
    )
    errors = []
    c.error.connect(errors.append)
    c.request_translation("merhaba")
    c.request_enhanced_prompt("merhaba")
    assert len(errors) == 2 and all("LLM" in e for e in errors)
    assert llm.calls == []


def test_set_llm_replaces_provider(qtbot):
    c = DictationController(
        Settings(), recorder=FakeRecorder(), stt=FakeStt(), llm=FakeLlm(), pool=QThreadPool()
    )
    new = FakeLlm()
    c.set_llm(new)
    c.request_translation("merhaba")
    qtbot.waitUntil(lambda: bool(new.calls), timeout=3000)


def test_limit_reached_stops_and_transcribes(ctl):
    c, rec, *_ = ctl
    c.toggle()
    assert c.state is DictationState.RECORDING
    rec.limit_reached.emit()
    assert c.state is DictationState.TRANSCRIBING and rec.stopped


def test_limit_reached_ignored_when_not_recording(ctl):
    c, rec, *_ = ctl
    rec.limit_reached.emit()
    assert c.state is DictationState.IDLE


class BlockingStt(FakeStt):
    """transcribe() serbest bırakılana kadar bekler; geç gelen sonucu test etmek için."""

    def __init__(self, text="merhaba dünya"):
        super().__init__(text)
        self.gate = threading.Event()

    def transcribe(self, audio, language=None):
        self.gate.wait(timeout=5)
        return TranscriptResult(self.text, "tr", 1.0, ())

    def release(self):
        self.gate.set()


def test_cancel_while_recording_discards_audio_and_goes_idle(ctl):
    c, rec, *_ = ctl
    c.toggle()
    c.cancel()
    assert c.state is DictationState.IDLE
    assert rec.stopped
    assert c.session.raw_text == ""


def test_cancel_while_transcribing_ignores_late_result(qtbot):
    stt = BlockingStt()
    c = DictationController(
        Settings(), recorder=FakeRecorder(), stt=stt, llm=FakeLlm(), pool=QThreadPool()
    )
    c.toggle()
    c.toggle()
    assert c.state is DictationState.TRANSCRIBING
    c.cancel()
    assert c.state is DictationState.IDLE
    stt.release()
    qtbot.wait(200)
    assert c.state is DictationState.IDLE
    assert c.session.raw_text == ""


def test_cancel_in_idle_is_noop(ctl):
    c, *_ = ctl
    fired = []
    c.cancelled.connect(lambda: fired.append(1))
    c.cancel()
    assert fired == [] and c.state is DictationState.IDLE


def test_cancel_emits_cancelled_signal(ctl):
    c, *_ = ctl
    fired = []
    c.cancelled.connect(lambda: fired.append(1))
    c.toggle()
    c.cancel()
    assert fired == [1]


def test_cancel_in_result_state_is_noop(ctl, qtbot):
    c, *_ = ctl
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)
    c.cancel()
    assert c.state is DictationState.RESULT
