import pytest
from PySide6.QtGui import QKeySequence

from dikte.config import DictionaryEntry, Settings
from dikte.ui.settings_dialog import SettingsDialog

TAB_TITLES = [
    "Genel",
    "Ses",
    "Konuşma Tanıma",
    "Metin Düzeltme",
    "Sözlük",
    "Gelişmiş",
    "Hakkında",
]


@pytest.fixture
def dlg(qtbot):
    d = SettingsDialog(Settings(), ())
    qtbot.addWidget(d)
    return d


def test_dialog_has_six_tabs(dlg):
    assert [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())] == TAB_TITLES


def test_advanced_fields_round_trip(dlg):
    dlg.beam_spin.setValue(2)
    dlg.vad_check.setChecked(False)
    dlg.initial_prompt_edit.setPlainText("X")
    dlg.num_ctx_spin.setValue(4096)
    dlg.top_p_spin.setValue(0.9)
    dlg.top_k_spin.setValue(40)
    dlg.timeout_spin.setValue(60)
    dlg.think_check.setChecked(True)
    s = dlg.result_settings()
    assert (s.stt.beam_size, s.stt.vad_filter, s.stt.initial_prompt) == (2, False, "X")
    assert (s.llm.num_ctx, s.llm.top_p, s.llm.top_k) == (4096, 0.9, 40)
    assert (s.llm.timeout_s, s.llm.think) == (60.0, True)


def test_hotkey_capture_writes_spec(dlg):
    dlg.hotkey_edit.setKeySequence(QKeySequence("Ctrl+Shift+D"))
    assert dlg.result_settings().hotkey == "ctrl+shift+d"


def test_provider_groups_follow_selection(dlg):
    dlg.provider_combo.setCurrentText("anthropic")
    assert not dlg.ollama_group.isVisibleTo(dlg.llm) and dlg.anthropic_group.isVisibleTo(dlg.llm)
    dlg.provider_combo.setCurrentText("ollama")
    assert dlg.ollama_group.isVisibleTo(dlg.llm) and not dlg.anthropic_group.isVisibleTo(dlg.llm)


def test_privacy_warning_only_for_remote_providers(dlg):
    assert not dlg.privacy_label.isVisibleTo(dlg.llm)
    dlg.provider_combo.setCurrentText("anthropic")
    assert dlg.privacy_label.isVisibleTo(dlg.llm)


def test_reload_hint_present_on_stt_model(dlg):
    assert "yeniden yüklenir" in dlg.stt_model_edit.toolTip().lower()


def test_max_seconds_special_text(dlg):
    assert dlg.max_seconds_spin.specialValueText() == "Sınırsız"


def test_silence_stop_special_text(dlg):
    assert dlg.silence_stop_spin.specialValueText() == "Kapalı"


def test_silence_stop_round_trip(dlg):
    dlg.silence_stop_spin.setValue(2.5)
    s = dlg.result_settings()
    assert s.audio.silence_stop_s == 2.5


def test_warm_up_and_prewarm_round_trip(dlg):
    dlg.warm_up_check.setChecked(False)
    dlg.prewarm_check.setChecked(False)
    s = dlg.result_settings()
    assert s.stt.warm_up is False and s.llm.prewarm is False


def test_empty_stt_model_blocks_accept_and_switches_tab(dlg):
    dlg.stt_model_edit.setText("   ")
    dlg.accept()
    assert "STT model" in dlg.error_label.text()
    assert dlg.tabs.currentWidget() is dlg.stt


def test_empty_llm_model_blocks_accept(dlg):
    dlg.llm_model_edit.setText("")
    dlg.accept()
    assert "LLM model" in dlg.error_label.text()
    assert dlg.tabs.currentWidget() is dlg.llm


def test_disabled_llm_skips_model_validation(dlg):
    dlg.llm_enabled_check.setChecked(False)
    dlg.llm_model_edit.setText("")
    assert dlg.llm.validate() is None


def test_about_tab_lists_versions(dlg):
    labels = dlg.about.findChildren(type(dlg.gpu_label))
    texts = " ".join(label.text() for label in labels)
    assert "Dikte" in texts and dlg.gpu_label.text()


def test_microphone_test_button_starts_and_stops_recorder(dlg, qtbot):
    class FakeRecorder:
        instances = []

        def __init__(self):
            self.started = self.stopped = False
            FakeRecorder.instances.append(self)

        @property
        def level_changed(self):
            class Sig:
                @staticmethod
                def connect(_slot):
                    return None

            return Sig()

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    dlg.audio._recorder_factory = FakeRecorder
    dlg.test_btn.setChecked(True)
    assert FakeRecorder.instances[-1].started
    dlg.test_btn.setChecked(False)
    assert FakeRecorder.instances[-1].stopped


def test_reject_stops_microphone_test(dlg):
    stopped = []
    dlg.audio.stop_test = lambda: stopped.append(1)
    dlg.reject()
    assert stopped == [1]


def test_provider_combo_lists_all_options(dlg):
    options = [dlg.provider_combo.itemText(i) for i in range(dlg.provider_combo.count())]
    assert options == ["ollama", "lmstudio", "openai", "anthropic", "gemini", "custom"]


def test_custom_group_fields_round_trip(dlg):
    dlg.provider_combo.setCurrentText("custom")
    assert dlg.custom_group.isVisibleTo(dlg.llm)
    dlg.custom_format_combo.setCurrentText("anthropic")
    dlg.custom_base_url_edit.setText("http://localhost:1234")
    dlg.custom_model_edit.setText("yerel-model")
    dlg.custom_key_env_edit.setText("LOCAL_KEY")
    s = dlg.result_settings()
    assert s.llm.provider == "custom" and s.llm.custom_format == "anthropic"
    assert s.llm.custom_base_url == "http://localhost:1234"
    assert s.llm.custom_model == "yerel-model" and s.llm.custom_api_key_env == "LOCAL_KEY"


def test_custom_without_url_blocks_accept(dlg):
    dlg.provider_combo.setCurrentText("custom")
    dlg.accept()
    assert "base URL" in dlg.error_label.text()


def test_key_status_shows_presence_not_value(dlg, monkeypatch):
    monkeypatch.setenv("TEST_KEY_ENV", "çok-gizli")
    dlg.openai_key_env_edit.setText("TEST_KEY_ENV")
    assert dlg.llm.openai_key_status.text() == "✓ tanımlı"
    monkeypatch.delenv("TEST_KEY_ENV")
    dlg.openai_key_env_edit.setText("TEST_KEY_ENV ")
    assert dlg.llm.openai_key_status.text() == "✗ yok"


def test_remote_provider_models_round_trip(dlg):
    dlg.provider_combo.setCurrentText("gemini")
    dlg.gemini_model_edit.setText("gemini-3.5-pro")
    dlg.gemini_key_env_edit.setText("MY_GEMINI")
    s = dlg.result_settings()
    assert s.llm.gemini_model == "gemini-3.5-pro" and s.llm.gemini_api_key_env == "MY_GEMINI"


def test_vad_group_fields_round_trip(dlg):
    dlg.vad_threshold_spin.setValue(0.65)
    dlg.vad_min_silence_spin.setValue(1500)
    dlg.no_speech_spin.setValue(0.8)
    dlg.hallucination_filter_check.setChecked(False)
    s = dlg.result_settings()
    assert s.stt.vad_threshold == 0.65 and s.stt.vad_min_silence_ms == 1500
    assert s.stt.no_speech_threshold == 0.8 and s.stt.hallucination_filter is False


def test_advanced_stt_thresholds_round_trip(dlg):
    dlg.vad_speech_pad_spin.setValue(450)
    dlg.log_prob_spin.setValue(-0.8)
    dlg.hallucination_silence_spin.setValue(3.5)
    s = dlg.result_settings()
    assert s.stt.vad_speech_pad_ms == 450
    assert s.stt.log_prob_threshold == -0.8
    assert s.stt.hallucination_silence_threshold_s == 3.5


def test_vad_checkbox_lives_only_on_the_stt_tab(dlg):
    """Tek kaynak: VAD kutusu yalnızca Konuşma Tanıma sekmesinde."""
    assert dlg.vad_check is dlg.stt.vad_check
    assert not hasattr(dlg.advanced, "vad_check")
    dlg.vad_check.setChecked(False)
    assert dlg.result_settings().stt.vad_filter is False


def test_openai_requires_base_url(dlg):
    dlg.provider_combo.setCurrentText("openai")
    dlg.openai_model_edit.setText("gpt-5.5")
    dlg.openai_base_url_edit.setText("   ")
    dlg.accept()
    assert "base URL" in dlg.error_label.text()
    assert dlg.tabs.currentWidget() is dlg.llm


def test_connection_test_button_reports_success(dlg, monkeypatch):
    import dikte.ui.settings.llm_tab as llm_tab_mod

    class FakeProvider:
        def complete(self, system, user):
            return "OK"

    monkeypatch.setattr(llm_tab_mod, "make_provider", lambda settings: FakeProvider())

    def fake_run_in_pool(fn, on_result, on_error, pool=None):
        try:
            on_result(fn())
        except Exception as exc:
            on_error(str(exc))

    monkeypatch.setattr(llm_tab_mod, "run_in_pool", fake_run_in_pool)

    dlg.provider_combo.setCurrentText("ollama")
    dlg.llm_model_edit.setText("qwen3.5:4b")
    dlg.llm_test_btn.click()
    assert "✓" in dlg.llm_test_status.text()
    assert dlg.llm_test_btn.isEnabled()


def test_connection_test_button_reports_failure(dlg, monkeypatch):
    import dikte.ui.settings.llm_tab as llm_tab_mod
    from dikte.llm.provider import LlmError

    class FailingProvider:
        def complete(self, system, user):
            raise LlmError("bağlantı yok")

    monkeypatch.setattr(llm_tab_mod, "make_provider", lambda settings: FailingProvider())

    def fake_run_in_pool(fn, on_result, on_error, pool=None):
        try:
            on_result(fn())
        except Exception as exc:
            on_error(str(exc))

    monkeypatch.setattr(llm_tab_mod, "run_in_pool", fake_run_in_pool)

    dlg.provider_combo.setCurrentText("ollama")
    dlg.llm_model_edit.setText("qwen3.5:4b")
    dlg.llm_test_btn.click()
    assert "✗" in dlg.llm_test_status.text()
    assert "bağlantı yok" in dlg.llm_test_status.text()


def test_connection_test_button_blocks_on_invalid_settings(dlg):
    dlg.provider_combo.setCurrentText("openai")
    dlg.openai_model_edit.setText("gpt-5.5")
    dlg.openai_base_url_edit.setText("   ")
    dlg.llm_test_btn.click()
    assert "✗" in dlg.llm_test_status.text()


def test_lmstudio_group_round_trip(dlg):
    dlg.provider_combo.setCurrentText("lmstudio")
    assert dlg.lmstudio_group.isVisibleTo(dlg.llm)
    assert dlg.lmstudio_base_url_edit.text() == "http://127.0.0.1:1234/v1"
    dlg.lmstudio_model_edit.setText("qwen3.5-4b")
    dlg.lmstudio_base_url_edit.setText("http://127.0.0.1:1235/v1")
    s = dlg.result_settings()
    assert s.llm.provider == "lmstudio" and s.llm.lmstudio_model == "qwen3.5-4b"
    assert s.llm.lmstudio_base_url == "http://127.0.0.1:1235/v1"


def test_lmstudio_is_local_so_no_privacy_warning(dlg):
    dlg.provider_combo.setCurrentText("lmstudio")
    assert not dlg.privacy_label.isVisibleTo(dlg.llm)


def test_empty_lmstudio_model_blocks_accept(dlg):
    dlg.provider_combo.setCurrentText("lmstudio")
    dlg.lmstudio_model_edit.setText("")
    dlg.accept()
    assert "model adı" in dlg.error_label.text() and dlg.tabs.currentWidget() is dlg.llm


def test_empty_ollama_host_blocks_accept(dlg):
    dlg.ollama_host_edit.setText("  ")
    dlg.accept()
    assert "host" in dlg.error_label.text().lower()


def test_sounds_check_unchecked_disables_sounds(dlg):
    dlg.sounds_check.setChecked(False)
    assert dlg.result_settings().sounds_enabled is False


def test_restore_clipboard_round_trip(dlg):
    dlg.auto_paste_check.setChecked(True)
    dlg.restore_clipboard_check.setChecked(True)
    assert dlg.result_settings().restore_clipboard is True


def test_restore_clipboard_disabled_when_auto_paste_off(dlg):
    dlg.auto_paste_check.setChecked(False)
    assert not dlg.restore_clipboard_check.isEnabled()


def test_push_to_talk_round_trip(dlg):
    dlg.push_to_talk_check.setChecked(False)
    assert dlg.result_settings().push_to_talk is False


def test_mode_hotkeys_default_to_empty(dlg):
    s = dlg.result_settings()
    assert s.hotkey_translate == "" and s.hotkey_prompt == ""


def test_translate_hotkey_round_trip(dlg):
    dlg.hotkey_translate_edit.setKeySequence(QKeySequence("Ctrl+Alt+T"))
    assert dlg.result_settings().hotkey_translate == "ctrl+alt+t"


def test_same_hotkey_for_two_modes_blocks_accept(dlg):
    dlg.hotkey_translate_edit.setKeySequence(dlg.hotkey_edit.keySequence())
    dlg.accept()
    assert "farklı olmalı" in dlg.error_label.text()


def test_open_location_failure_warns_user(dlg, monkeypatch):
    """QDesktopServices açamazsa sessiz kalınmaz; yolu içeren bir uyarı gösterilir."""
    from dikte.ui.settings import about_tab as about_mod

    monkeypatch.setattr(about_mod.QDesktopServices, "openUrl", staticmethod(lambda _url: False))
    warned = []
    monkeypatch.setattr(
        about_mod.QMessageBox, "warning", staticmethod(lambda *a: warned.append(a[2]))
    )
    dlg.about.open_log_btn.click()
    assert warned and "açılamadı" in warned[0]


def test_microphone_test_failure_resets_button_and_warns(dlg, monkeypatch):
    """Cihaz açılamazsa test düğmesi basılı kalmaz ve kullanıcı yönlendirilir."""
    from dikte.ui.settings import audio_tab as audio_mod

    warned = []
    monkeypatch.setattr(
        audio_mod.QMessageBox, "warning", staticmethod(lambda *a: warned.append(a[2]))
    )

    def boom():
        raise OSError("cihaz meşgul")

    dlg.audio._recorder_factory = boom
    dlg.test_btn.setChecked(True)
    assert not dlg.test_btn.isChecked()
    assert dlg.test_btn.text() == "Mikrofonu test et"
    assert warned and "cihaz meşgul" in warned[0]


def test_dictionary_round_trip(dlg):
    dlg.dictionary.add_entry_btn.click()
    row = dlg.dictionary_table.rowCount() - 1
    dlg.dictionary_table.item(row, 0).setText("Kubernetes")
    dlg.dictionary_table.item(row, 1).setText("kuber netes, kübernetes")
    dlg.instructions_edit.setPlainText("Kısa tut")
    s = dlg.result_settings()
    assert s.dictionary.entries == (
        DictionaryEntry(term="Kubernetes", wrong=("kuber netes", "kübernetes")),
    )
    assert s.dictionary.user_instructions == "Kısa tut"


def test_dictionary_rejects_empty_term(dlg):
    dlg.dictionary.add_entry_btn.click()
    assert dlg.dictionary.validate() == "Sözlükte boş terim var"
