import pytest
from PySide6.QtGui import QKeySequence

from dikte.config import Settings
from dikte.ui.settings_dialog import SettingsDialog

TAB_TITLES = ["Genel", "Ses", "Konuşma Tanıma", "Metin Düzeltme", "Gelişmiş", "Hakkında"]


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


def test_restart_hint_present_on_stt_model(dlg):
    assert "yeniden başlat" in dlg.stt_model_edit.toolTip().lower()


def test_max_seconds_special_text(dlg):
    assert dlg.max_seconds_spin.specialValueText() == "Sınırsız"


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


def test_provider_combo_lists_five_options(dlg):
    options = [dlg.provider_combo.itemText(i) for i in range(dlg.provider_combo.count())]
    assert options == ["ollama", "openai", "anthropic", "gemini", "custom"]


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
