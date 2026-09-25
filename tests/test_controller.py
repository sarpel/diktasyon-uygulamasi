import json
import threading

import numpy as np
import pytest
from PySide6.QtCore import QObject, QThreadPool, Signal

from dikte.config import AppProfile, DictionaryEntry, DictionarySettings, Settings
from dikte.core.controller import DictationController
from dikte.core.state import DictationState
from dikte.stt.result import TranscriptResult


class FakeRecorder(QObject):
    level_changed = Signal(float)
    buckets_changed = Signal(object)
    limit_reached = Signal()
    silence_reached = Signal()
    chunk_ready = Signal(object)
    error = Signal(str)
    warning = Signal(str)

    def __init__(self, fail_to_start=False):
        super().__init__()
        self.started = self.stopped = False
        self.chunks_emitted = 0  # gerçek kayıtçı durdurma anına kadar kestiği parça sayısı
        self.audio = np.ones(16000, dtype=np.float32) * 0.1
        self.chunking = None
        self._fail_to_start = fail_to_start
        self._recording = False

    @property
    def is_recording(self):
        return self._recording

    def start(self):
        self.started = True
        self.chunks_emitted = 0
        if self._fail_to_start:
            self.error.emit("mikrofon açılamadı")
            return
        self._recording = True

    def stop(self):
        self.stopped = True
        self._recording = False
        return self.audio

    def set_chunking(self, chunk_s, max_chunk_s):
        self.chunking = (chunk_s, max_chunk_s)


class FakeStt:
    def __init__(self, text="merhaba dünya"):
        self.text, self.loaded, self.warmed = text, False, False

    @property
    def is_loaded(self):
        return self.loaded

    @property
    def active_model(self) -> str:
        return "fake"

    def load(self):
        self.loaded = True

    def warm_up(self):
        self.load()
        self.warmed = True

    def transcribe(self, audio, language=None, **kwargs):
        return TranscriptResult(self.text, "tr", 1.0, ())


class FakeLlm:
    name = "fake"

    def __init__(self):
        self.calls = []
        self.warmed = False

    def warm_up(self):
        self.warmed = True

    def complete(self, system, user, *, json_schema=None, temperature=0.2):
        self.calls.append({"system": system, "user": user})
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


def test_translate_mode_chains_translation_and_emits_it(ctl, qtbot):
    c, rec, stt, llm = ctl
    results = []
    c.result_ready.connect(results.append)
    c.toggle("translate")
    assert c.state is DictationState.RECORDING and rec.started
    c.toggle("translate")
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert results == ["Hello world."]
    assert c.session.mode == "translate"
    assert c.session.translation == "Hello world."


def test_prompt_mode_chains_enhanced_prompt_and_emits_it(ctl, qtbot):
    c, rec, stt, llm = ctl
    results = []
    c.result_ready.connect(results.append)
    c.toggle("prompt")
    c.toggle("prompt")
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert results and results[0].startswith("# Goal")
    assert c.session.mode == "prompt"
    assert c.session.enhanced_prompt.startswith("# Goal")


def test_mode_with_llm_disabled_emits_error_and_raw(qtbot):
    settings, _ = _disabled_llm_settings()
    rec, stt, llm = FakeRecorder(), FakeStt(), FakeLlm()
    c = DictationController(settings, recorder=rec, stt=stt, llm=llm, pool=QThreadPool())
    errors, results = [], []
    c.error.connect(errors.append)
    c.result_ready.connect(results.append)
    c.toggle("prompt")
    c.toggle("prompt")
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert errors and "LLM kapalı" in errors[-1]
    assert results == ["merhaba dünya"]
    assert llm.calls == []


def test_dictionary_rules_applied_and_glossary_sent_to_llm(qtbot):
    entries = (DictionaryEntry(term="Kubernetes", wrong=("kuber netes",)),)
    settings = Settings(
        dictionary=DictionarySettings(entries=entries, user_instructions="Kısa tut")
    )
    rec, stt, llm = FakeRecorder(), FakeStt(text="kuber netes"), FakeLlm()
    c = DictationController(settings, recorder=rec, stt=stt, llm=llm, pool=QThreadPool())
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert c.session.raw_text == "Kubernetes"
    assert "Kubernetes" in llm.calls[0]["system"]
    assert "Kısa tut" in llm.calls[0]["system"]


def test_voice_commands_applied_when_enabled(qtbot):
    rec, stt, llm = FakeRecorder(), FakeStt(text="merhaba yeni satır nasılsın"), FakeLlm()
    c = DictationController(Settings(), recorder=rec, stt=stt, llm=llm, pool=QThreadPool())
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert c.session.raw_text == "merhaba\nNasılsın"


def test_voice_commands_left_untouched_when_disabled(qtbot):
    settings = Settings(voice_commands=False)
    rec, stt, llm = FakeRecorder(), FakeStt(text="merhaba yeni satır nasılsın"), FakeLlm()
    c = DictationController(settings, recorder=rec, stt=stt, llm=llm, pool=QThreadPool())
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert c.session.raw_text == "merhaba yeni satır nasılsın"


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


def test_silence_signal_stops_recording(ctl):
    c, rec, *_ = ctl
    c.toggle()
    assert c.state is DictationState.RECORDING
    rec.silence_reached.emit()
    assert c.state is DictationState.TRANSCRIBING and rec.stopped


def test_start_recording_from_idle_starts(ctl):
    c, rec, *_ = ctl
    c.start_recording()
    assert c.state is DictationState.RECORDING and rec.started


def test_start_recording_stays_idle_when_microphone_fails_to_open(qtbot):
    rec, stt, llm = FakeRecorder(fail_to_start=True), FakeStt(), FakeLlm()
    c = DictationController(Settings(), recorder=rec, stt=stt, llm=llm, pool=QThreadPool())
    errors = []
    c.error.connect(errors.append)
    c.start_recording()
    assert c.state is DictationState.IDLE
    assert errors == ["mikrofon açılamadı"]


def test_start_recording_while_recording_is_a_no_op(ctl):
    c, rec, *_ = ctl
    c.start_recording()
    rec.started = False
    c.start_recording()
    assert c.state is DictationState.RECORDING and not rec.started


def test_stop_recording_while_idle_is_a_no_op(ctl):
    c, rec, *_ = ctl
    c.stop_recording()
    assert c.state is DictationState.IDLE and not rec.stopped


def test_stop_recording_while_recording_transcribes(ctl):
    c, rec, *_ = ctl
    c.start_recording()
    c.stop_recording()
    assert c.state is DictationState.TRANSCRIBING and rec.stopped


def test_transcribe_file_reaches_result_with_source_path(qtbot):
    loaded = []

    def loader(path):
        loaded.append(path)
        return np.ones(16000, dtype=np.float32)

    c = DictationController(
        Settings(),
        recorder=FakeRecorder(),
        stt=FakeStt(),
        llm=FakeLlm(),
        pool=QThreadPool(),
        audio_loader=loader,
    )
    c.transcribe_file("/tmp/a.wav")
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert c.session.source_path == "/tmp/a.wav"
    assert loaded == ["/tmp/a.wav"]


def test_transcribe_file_rejected_while_busy(ctl):
    c, rec, *_ = ctl
    c.toggle()  # kayıt başlar, meşgul olur
    errors = []
    c.error.connect(errors.append)
    c.transcribe_file("/tmp/a.wav")
    assert errors == ["Önce süren işi bitirin."]
    assert c.state is DictationState.RECORDING


def test_transcribe_file_error_emits_message(qtbot):
    def boom(path):
        raise OSError("bozuk dosya")

    c = DictationController(
        Settings(),
        recorder=FakeRecorder(),
        stt=FakeStt(),
        llm=FakeLlm(),
        pool=QThreadPool(),
        audio_loader=boom,
    )
    errors = []
    c.error.connect(errors.append)
    c.transcribe_file("/tmp/bad.wav")
    qtbot.waitUntil(lambda: bool(errors), timeout=3000)
    assert "Dosya çözümlenemedi" in errors[0]


class BlockingStt(FakeStt):
    """transcribe() serbest bırakılana kadar bekler; geç gelen sonucu test etmek için."""

    def __init__(self, text="merhaba dünya"):
        super().__init__(text)
        self.gate = threading.Event()

    def transcribe(self, audio, language=None, **kwargs):
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


class BlockingLlm(FakeLlm):
    """complete() serbest bırakılana kadar bekler; geç gelen çeviri sonucunu test etmek için."""

    def __init__(self):
        super().__init__()
        self.gate = threading.Event()

    def complete(self, system, user, *, json_schema=None, temperature=0.2):
        self.gate.wait(timeout=5)
        return super().complete(system, user, json_schema=json_schema, temperature=temperature)

    def release(self):
        self.gate.set()


def test_stale_translation_does_not_stick_to_next_session(qtbot):
    """F013: bir oturumdayken istenen çeviri, yanıt gelmeden yeni bir kayıt başlarsa
    yeni oturuma yapışmamalı (_gen kuşak sayacı bu isteği de geçersiz kılmalı)."""
    c = DictationController(
        Settings(), recorder=FakeRecorder(), stt=FakeStt(), llm=FakeLlm(), pool=QThreadPool()
    )
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RECORDING, timeout=3000)
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    llm = BlockingLlm()
    c.set_llm(llm)
    c.request_translation("eski metin")
    c.start_recording()  # yanıt gelmeden yeni bir oturum başlatılıyor
    assert c.state is DictationState.RECORDING
    llm.release()
    qtbot.wait(300)
    assert c.session.translation == ""


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


def test_warm_up_calls_stt_and_llm_warm_up(qtbot):
    stt, llm = FakeStt(), FakeLlm()
    c = DictationController(
        Settings(), recorder=FakeRecorder(), stt=stt, llm=llm, pool=QThreadPool()
    )
    ready = []
    c.ready_changed.connect(ready.append)
    c.warm_up()
    qtbot.waitUntil(lambda: ready == [True], timeout=3000)
    qtbot.waitUntil(lambda: llm.warmed, timeout=3000)
    assert stt.warmed


def test_warm_up_skips_llm_when_disabled(qtbot):
    settings, _ = _disabled_llm_settings()
    llm = FakeLlm()
    c = DictationController(
        settings, recorder=FakeRecorder(), stt=FakeStt(), llm=llm, pool=QThreadPool()
    )
    c.warm_up()
    qtbot.wait(150)
    assert not llm.warmed


def test_prewarm_llm_runs_after_provider_change(qtbot):
    c = DictationController(
        Settings(), recorder=FakeRecorder(), stt=FakeStt(), llm=FakeLlm(), pool=QThreadPool()
    )
    new = FakeLlm()
    c.set_llm(new)
    c.prewarm_llm()
    qtbot.waitUntil(lambda: new.warmed, timeout=3000)


def test_result_ready_emitted_after_result_state(qtbot):
    settings, _ = _disabled_llm_settings()
    c = DictationController(
        settings, recorder=FakeRecorder(), stt=FakeStt(), llm=FakeLlm(), pool=QThreadPool()
    )
    order = []
    c.state_changed.connect(lambda s: order.append(("state", s)))
    c.result_ready.connect(lambda t: order.append(("text", t)))
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: ("text", "merhaba dünya") in order, timeout=5000)
    assert order.index(("state", DictationState.RESULT)) < order.index(("text", "merhaba dünya"))


def test_result_ready_emits_corrected_text(ctl, qtbot):
    c, *_ = ctl
    texts = []
    c.result_ready.connect(texts.append)
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: texts == ["Merhaba dünya."], timeout=5000)


def test_result_ready_emits_raw_text_when_llm_fails(qtbot):
    class BadLlm(FakeLlm):
        def complete(self, *a, **k):
            raise RuntimeError("down")

    c = DictationController(
        Settings(), recorder=FakeRecorder(), stt=FakeStt(), llm=BadLlm(), pool=QThreadPool()
    )
    texts = []
    c.result_ready.connect(texts.append)
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: texts == ["merhaba dünya"], timeout=5000)


def test_apply_edit_ignored_outside_result(ctl):
    c, *_ = ctl
    assert c.state is DictationState.IDLE
    c.apply_edit("yeni metin")
    assert c.session.corrected_text == ""


def test_apply_edit_updates_session_in_result(ctl, qtbot):
    c, *_ = ctl
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)
    c.apply_edit("Merhaba dünya, düzenlendi.")
    assert c.session.corrected_text == "Merhaba dünya, düzenlendi."


def test_apply_edit_emits_edit_learned_when_changed(ctl, qtbot):
    c, *_ = ctl
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)
    changes = []
    c.edit_learned.connect(changes.append)
    c.apply_edit("Merhaba dünyalar.")
    assert len(changes) == 1 and len(changes[0]) > 0


def test_apply_edit_no_signal_when_unchanged(ctl, qtbot):
    c, *_ = ctl
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)
    changes = []
    c.edit_learned.connect(changes.append)
    c.apply_edit(c.session.corrected_text)
    assert changes == []


def test_profile_overrides_mode_and_tags_session(ctl, qtbot):
    c, rec, stt, llm = ctl
    results = []
    c.result_ready.connect(results.append)
    profile = AppProfile(name="Terminal", match="wt", mode="translate")
    c.toggle(profile=profile)
    assert c.session.mode == "translate" and c.session.profile == "Terminal"
    c.toggle(profile=profile)
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert results == ["Hello world."]


def test_profile_llm_disabled_skips_correction(ctl, qtbot):
    c, rec, stt, llm = ctl
    profile = AppProfile(name="Terminal", match="wt", llm_enabled=False)
    states = []
    c.state_changed.connect(states.append)
    c.toggle(profile=profile)
    c.toggle(profile=profile)
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert DictationState.CORRECTING not in states
    assert c.session.corrected_text == "merhaba dünya"
    assert llm.calls == []


def test_profile_with_default_mode_does_not_override_explicit_mode(ctl, qtbot):
    c, rec, stt, llm = ctl
    profile = AppProfile(name="Terminal", match="wt", mode="translate")
    c.toggle("prompt", profile=profile)
    assert c.session.mode == "prompt"
    c.toggle("prompt", profile=profile)
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)


def test_transcribe_file_ignores_stale_active_profile(qtbot):
    profile = AppProfile(name="Terminal", match="wt", llm_enabled=False)
    rec, stt, llm = FakeRecorder(), FakeStt(), FakeLlm()
    c = DictationController(
        Settings(),
        recorder=rec,
        stt=stt,
        llm=llm,
        pool=QThreadPool(),
        audio_loader=lambda path: np.ones(16000, dtype=np.float32),
    )
    c.toggle(profile=profile)
    c.cancel()
    c.transcribe_file("/tmp/x.wav")
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert c.session.corrected_text == "Merhaba dünya."
    assert llm.calls != []


def _live_chunk_settings(live_chunk_s=1.0, live_max_chunk_s=45.0):
    s = Settings()
    return s.model_copy(
        update={
            "stt": s.stt.model_copy(
                update={"live_chunk_s": live_chunk_s, "live_max_chunk_s": live_max_chunk_s}
            )
        }
    )


class SequentialStt(FakeStt):
    """Ardışık çağrılarda sırayla farklı metinler döndürür (canlı-parça testleri için)."""

    def __init__(self, texts):
        super().__init__(texts[0] if texts else "")
        self._texts = list(texts)
        self.calls: list[str] = []

    def transcribe(self, audio, language=None, **kwargs):
        self.calls.append(kwargs.get("previous_text", ""))
        return TranscriptResult(self._texts.pop(0), "tr", 1.0, ())


def test_controller_configures_recorder_chunking_on_init():
    rec = FakeRecorder()
    DictationController(Settings(), recorder=rec, stt=FakeStt(), llm=FakeLlm(), pool=QThreadPool())
    assert rec.chunking == (20.0, 45.0)


def test_update_settings_reconfigures_recorder_chunking():
    rec = FakeRecorder()
    c = DictationController(
        Settings(), recorder=rec, stt=FakeStt(), llm=FakeLlm(), pool=QThreadPool()
    )
    c.update_settings(_live_chunk_settings(live_chunk_s=5.0))
    assert rec.chunking == (5.0, 45.0)


def test_live_chunk_s_zero_uses_single_pass_path(qtbot):
    rec, stt, llm = FakeRecorder(), FakeStt(), FakeLlm()
    c = DictationController(
        _live_chunk_settings(live_chunk_s=0), recorder=rec, stt=stt, llm=llm, pool=QThreadPool()
    )
    partials = []
    c.partial_text.connect(partials.append)
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert partials == []
    assert c.session.raw_text == "merhaba dünya"


def test_live_chunking_joins_partial_texts_in_order(qtbot):
    rec = FakeRecorder()
    stt = SequentialStt(["Birinci parça.", "İkinci parça.", "Üçüncü parça."])
    llm = FakeLlm()
    c = DictationController(
        _live_chunk_settings(), recorder=rec, stt=stt, llm=llm, pool=QThreadPool()
    )
    partials = []
    c.partial_text.connect(partials.append)
    c.toggle()
    rec.chunk_ready.emit(np.ones(1600, dtype=np.float32) * 0.1)
    qtbot.waitUntil(lambda: len(partials) == 1, timeout=3000)
    rec.chunk_ready.emit(np.ones(1600, dtype=np.float32) * 0.1)
    qtbot.waitUntil(lambda: len(partials) == 2, timeout=3000)
    assert partials == ["Birinci parça.", "Birinci parça. İkinci parça."]
    c.toggle()  # durdur: kuyruktaki son parça da aynı yolla gönderilir
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert c.session.raw_text == "Birinci parça. İkinci parça. Üçüncü parça."
    assert stt.calls == ["", "Birinci parça.", "Birinci parça. İkinci parça."]


def test_chunk_ready_ignored_when_not_recording(qtbot):
    rec, stt, llm = FakeRecorder(), FakeStt(), FakeLlm()
    c = DictationController(
        _live_chunk_settings(), recorder=rec, stt=stt, llm=llm, pool=QThreadPool()
    )
    partials = []
    c.partial_text.connect(partials.append)
    rec.chunk_ready.emit(np.ones(1600, dtype=np.float32) * 0.1)
    qtbot.wait(200)
    assert partials == []


def test_live_chunk_error_sets_idle_and_emits_error(qtbot):
    class FailingStt(FakeStt):
        def transcribe(self, audio, language=None, **kwargs):
            raise RuntimeError("çözümleme koptu")

    rec = FakeRecorder()
    c = DictationController(
        _live_chunk_settings(),
        recorder=rec,
        stt=FailingStt(),
        llm=FakeLlm(),
        pool=QThreadPool(),
    )
    errors = []
    c.error.connect(errors.append)
    c.toggle()
    rec.chunk_ready.emit(np.ones(1600, dtype=np.float32) * 0.1)
    qtbot.waitUntil(lambda: c.state is DictationState.IDLE, timeout=3000)
    assert errors and "çözümleme koptu" in errors[-1]


def test_many_in_flight_jobs_all_deliver_callbacks(qtbot):
    """_track eskiden yalnızca son 16 sinyal nesnesini tutuyordu; 16'dan fazla eşzamanlı
    işte ilk işlerin sinyal nesneleri teslimattan önce çöpe gidip geri çağrılar kayboluyordu."""
    import gc
    import time

    llm = FakeLlm()
    pool = QThreadPool()
    pool.setMaxThreadCount(32)
    c = DictationController(Settings(), recorder=FakeRecorder(), stt=FakeStt(), llm=llm, pool=pool)
    delivered = []
    c.session_updated.connect(lambda s: delivered.append(s.translation))
    for i in range(24):
        c.request_translation(f"metin {i}")
    pool.waitForDone(5000)  # tüm işler bitti ve sonuçlarını kuyruğa koydu
    time.sleep(0.05)
    gc.collect()
    qtbot.waitUntil(lambda: len(delivered) == 24, timeout=3000)
    qtbot.waitUntil(lambda: len(c._jobs) == 0, timeout=3000)  # teslim edilen işler bırakılır


# ---- durdurma anında kuyrukta kalan parça (ses kaybı regresyonu)


def test_chunk_arriving_after_stop_is_not_lost(qtbot):
    """Kayıtçı, durdurmadan hemen önceki sessiz blokta bir parça keser; kuyruklu sinyali
    stop() sonrası (TRANSCRIBING) gelir. Eskiden atılıyordu: 45 sn'ye kadar konuşma kaybı."""
    rec = FakeRecorder()
    stt = SequentialStt(["Birinci.", "Gecikmiş.", "Kuyruk."])
    c = DictationController(
        _live_chunk_settings(), recorder=rec, stt=stt, llm=FakeLlm(), pool=QThreadPool()
    )
    partials = []
    c.partial_text.connect(partials.append)
    c.toggle()
    rec.chunks_emitted = 1
    rec.chunk_ready.emit(np.ones(1600, dtype=np.float32) * 0.1)
    qtbot.waitUntil(lambda: len(partials) == 1, timeout=3000)
    rec.chunks_emitted = 2  # ikinci parça kesildi ama sinyali henüz teslim edilmedi
    c.toggle()
    assert c.state is DictationState.TRANSCRIBING
    rec.chunk_ready.emit(np.ones(1600, dtype=np.float32) * 0.2)  # geç teslimat
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert c.session.raw_text == "Birinci. Gecikmiş. Kuyruk."
    assert stt.calls == ["", "Birinci.", "Birinci. Gecikmiş."]  # kuyruk en sonda


def test_missing_late_chunk_does_not_hang_forever(qtbot, monkeypatch):
    import dikte.core.controller as ctl_mod

    monkeypatch.setattr(ctl_mod, "LATE_CHUNK_TIMEOUT_MS", 50)
    rec = FakeRecorder()
    stt = SequentialStt(["Kuyruk."])
    c = DictationController(
        _live_chunk_settings(), recorder=rec, stt=stt, llm=FakeLlm(), pool=QThreadPool()
    )
    c.toggle()
    rec.chunks_emitted = 1  # parça kesildi ama hiç teslim edilmeyecek
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert c.session.raw_text == "Kuyruk."


def test_late_chunk_after_cancel_is_ignored(qtbot):
    rec = FakeRecorder()
    stt = SequentialStt(["x", "y"])
    c = DictationController(
        _live_chunk_settings(), recorder=rec, stt=stt, llm=FakeLlm(), pool=QThreadPool()
    )
    c.toggle()
    rec.chunks_emitted = 1
    c.toggle()
    c.cancel()
    rec.chunk_ready.emit(np.ones(1600, dtype=np.float32))
    qtbot.wait(100)
    assert c.state is DictationState.IDLE and stt.calls == []


# ---- kayıt ortasında ayar değişikliği


def test_chunk_mode_is_fixed_for_the_whole_recording(qtbot):
    rec = FakeRecorder()
    stt = SequentialStt(["Birinci.", "Son."])
    c = DictationController(
        _live_chunk_settings(), recorder=rec, stt=stt, llm=FakeLlm(), pool=QThreadPool()
    )
    partials = []
    c.partial_text.connect(partials.append)
    c.toggle()
    rec.chunks_emitted = 1
    rec.chunk_ready.emit(np.ones(1600, dtype=np.float32) * 0.1)
    qtbot.waitUntil(lambda: len(partials) == 1, timeout=3000)
    c.update_settings(_live_chunk_settings(live_chunk_s=0))
    assert rec.chunking == (1.0, 45.0)  # süren kayıtta parçalama değişmez
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert c.session.raw_text == "Birinci. Son."
    c.toggle()  # yeni kayıt: yeni ayar artık geçerli
    assert rec.chunking == (0, 45.0)


# ---- parça sırası ve bağlam


class GatedSequentialStt(SequentialStt):
    """İlk çağrı kapı açılana kadar bekler; sonraki çağrılar hemen döner."""

    def __init__(self, texts):
        super().__init__(texts)
        self.gate = threading.Event()
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def transcribe(self, audio, language=None, **kwargs):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            first = len(self.calls) == 0
        try:
            if first:
                self.gate.wait(timeout=5)
            return super().transcribe(audio, language, **kwargs)
        finally:
            with self._lock:
                self.active -= 1


def test_chunks_are_transcribed_in_order_with_gui_thread_context(qtbot):
    rec = FakeRecorder()
    stt = GatedSequentialStt(["A", "B", "C"])
    pool = QThreadPool()
    pool.setMaxThreadCount(4)
    c = DictationController(_live_chunk_settings(), recorder=rec, stt=stt, llm=FakeLlm(), pool=pool)
    c.toggle()
    rec.chunk_ready.emit(np.ones(1600, dtype=np.float32) * 0.1)
    rec.chunk_ready.emit(np.ones(1600, dtype=np.float32) * 0.1)
    rec.chunks_emitted = 2
    qtbot.wait(100)
    assert stt.max_active == 1  # ikinci parça, birincisi bitmeden başlamadı
    stt.gate.set()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert c.session.raw_text == "A B C"
    assert stt.calls == ["", "A", "A B"]
    assert stt.max_active == 1


# ---- kayıtçı uyarıları / hataları


def test_recorder_warning_is_forwarded(ctl):
    c, rec, *_ = ctl
    warnings = []
    c.warning.connect(warnings.append)
    rec.warning.emit("Mikrofondan ses gelmiyor.")
    assert warnings == ["Mikrofondan ses gelmiyor."]


def test_recorder_error_while_recording_stops_stream_and_goes_idle(ctl):
    c, rec, *_ = ctl
    c.toggle()
    errors = []
    c.error.connect(errors.append)
    rec.error.emit("Mikrofon bağlantısı kesildi")
    assert c.state is DictationState.IDLE and rec.stopped
    assert errors and errors[0].startswith("Mikrofon bağlantısı kesildi")


# ---- başarısız sesi saklama ve yeniden deneme


def _failing_ctl(tmp_path, stt, settings=None, recorder=None):
    return DictationController(
        settings or Settings(),
        recorder=recorder or FakeRecorder(),
        stt=stt,
        llm=FakeLlm(),
        pool=QThreadPool(),
        failed_audio_path=tmp_path / "failed" / "last.wav",
    )


class FailingStt(FakeStt):
    def transcribe(self, audio, language=None, **kwargs):
        raise RuntimeError("CUDA belleği doldu")


def test_failed_transcription_keeps_audio_and_hints_retry(qtbot, tmp_path):
    from dikte.audio.wav import load_wav

    c = _failing_ctl(tmp_path, FailingStt())
    errors, changed = [], []
    c.error.connect(errors.append)
    c.failed_audio_changed.connect(changed.append)
    assert not c.has_failed_audio
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.IDLE, timeout=3000)
    wav = tmp_path / "failed" / "last.wav"
    assert wav.exists() and c.has_failed_audio and changed == [True]
    assert load_wav(wav).shape == (16000,)
    assert "CUDA belleği doldu" in errors[-1] and "yeniden dene" in errors[-1]


def test_empty_transcription_keeps_audio(qtbot, tmp_path):
    c = _failing_ctl(tmp_path, FakeStt(text=""))
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.IDLE, timeout=3000)
    assert c.has_failed_audio


def test_failed_audio_not_kept_when_disabled(qtbot, tmp_path):
    c = _failing_ctl(tmp_path, FailingStt(), settings=Settings(keep_failed_audio=False))
    errors = []
    c.error.connect(errors.append)
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.IDLE, timeout=3000)
    assert not c.has_failed_audio and "yeniden dene" not in errors[-1]


def test_failed_live_chunk_session_keeps_all_chunks(qtbot, tmp_path):
    from dikte.audio.wav import load_wav

    rec = FakeRecorder()
    c = _failing_ctl(tmp_path, FakeStt(text=""), settings=_live_chunk_settings(), recorder=rec)
    c.toggle()
    rec.chunks_emitted = 1
    rec.chunk_ready.emit(np.ones(8000, dtype=np.float32) * 0.1)
    c.toggle()  # kuyruk: 16000 örnek
    qtbot.waitUntil(lambda: c.state is DictationState.IDLE, timeout=3000)
    assert load_wav(tmp_path / "failed" / "last.wav").shape == (24000,)


def test_retry_last_failed_runs_full_flow_and_deletes_file(qtbot, tmp_path):
    stt = FailingStt()
    c = _failing_ctl(tmp_path, stt)
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.IDLE, timeout=3000)
    seen = []
    stt.transcribe = lambda audio, language=None, **kw: (  # type: ignore[method-assign]
        seen.append(audio.shape) or TranscriptResult("merhaba dünya", "tr", 1.0, ())
    )
    results = []
    c.result_ready.connect(results.append)
    assert c.retry_last_failed() is True
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=3000)
    assert seen == [(16000,)]
    assert results == ["Merhaba dünya."]  # LLM düzeltmesi dahil normal akış
    assert not c.has_failed_audio


def test_retry_failure_keeps_file(qtbot, tmp_path):
    c = _failing_ctl(tmp_path, FailingStt())
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.IDLE, timeout=3000)
    assert c.retry_last_failed()
    qtbot.waitUntil(lambda: c.state is DictationState.IDLE, timeout=3000)
    assert c.has_failed_audio


def test_retry_without_file_returns_false(qtbot, tmp_path):
    c = _failing_ctl(tmp_path, FakeStt())
    errors = []
    c.error.connect(errors.append)
    assert c.retry_last_failed() is False
    assert errors == ["Yeniden denenecek kayıt yok."]


def test_retry_rejected_while_busy(qtbot, tmp_path):
    c = _failing_ctl(tmp_path, FakeStt())
    c.toggle()
    assert c.retry_last_failed() is False
    assert c.state is DictationState.RECORDING


def test_no_failed_audio_path_disables_feature(qtbot):
    c = DictationController(
        Settings(), recorder=FakeRecorder(), stt=FailingStt(), llm=FakeLlm(), pool=QThreadPool()
    )
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.IDLE, timeout=3000)
    assert not c.has_failed_audio


# ---- düzeltme sağlamlık kontrolü ve "geri al" sesli komutu


def _long_stt_ctl(settings):
    rec, stt, llm = FakeRecorder(), FakeStt("bir iki üç dört beş altı yedi sekiz"), FakeLlm()
    c = DictationController(settings, recorder=rec, stt=stt, llm=llm, pool=QThreadPool())
    return c, llm


def test_sanity_check_rejects_collapsed_correction(qtbot):
    c, _llm = _long_stt_ctl(Settings())
    errors = []
    c.error.connect(errors.append)
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)
    assert c.session.corrected_text == "bir iki üç dört beş altı yedi sekiz"
    assert errors


def test_sanity_check_off_accepts_correction(qtbot):
    s = Settings()
    s = s.model_copy(update={"llm": s.llm.model_copy(update={"sanity_check": False})})
    c, _llm = _long_stt_ctl(s)
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)
    assert c.session.corrected_text == "Merhaba dünya."


def test_undo_voice_command_requests_undo_instead_of_result(qtbot):
    rec, stt, llm = FakeRecorder(), FakeStt("Geri al."), FakeLlm()
    c = DictationController(Settings(), recorder=rec, stt=stt, llm=llm, pool=QThreadPool())
    undone, results = [], []
    c.undo_requested.connect(lambda: undone.append(True))
    c.result_ready.connect(results.append)
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: undone == [True], timeout=5000)
    assert c.state is DictationState.IDLE
    assert results == [] and llm.calls == []


def test_undo_phrase_is_plain_text_when_voice_commands_off(qtbot):
    rec, stt, llm = FakeRecorder(), FakeStt("Geri al."), FakeLlm()
    s = Settings(voice_commands=False)
    s = s.model_copy(update={"llm": s.llm.model_copy(update={"enabled": False})})
    c = DictationController(s, recorder=rec, stt=stt, llm=llm, pool=QThreadPool())
    c.toggle()
    c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)
    assert c.session.corrected_text == "Geri al."
