import pytest
from PySide6.QtGui import QKeySequence

from dikte.config import AppProfile, DictionaryEntry, Settings
from dikte.ui.settings_dialog import SettingsDialog

TAB_TITLES = [
    "Genel",
    "Ses",
    "Konuşma Tanıma",
    "Metin Düzeltme",
    "Sözlük",
    "Gelişmiş",
    "Profiller",
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


def test_voice_commands_checkbox_round_trips(dlg):
    assert dlg.voice_commands_check.isChecked() is True
    dlg.voice_commands_check.setChecked(False)
    assert dlg.result_settings().voice_commands is False


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


def test_about_tab_has_health_check_button(dlg):
    assert dlg.health_btn.text() == "Durum kontrolü…"


def test_about_tab_uses_injected_gpu_and_vram_probes(qtbot):
    from dikte.ui.settings.about_tab import AboutTab

    tab = AboutTab(Settings(), gpu_probe=lambda: "sahte GPU", vram_probe=lambda: "3,2 / 8,0 GB")
    qtbot.addWidget(tab)
    qtbot.waitUntil(lambda: tab.gpu_label.text() == "sahte GPU", timeout=3000)
    assert tab.vram_label.text() == "3,2 / 8,0 GB"


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
    dlg.custom_format_combo.setCurrentIndex(dlg.custom_format_combo.findData("anthropic"))
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
    assert "temel URL" in dlg.error_label.text()


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
    s = dlg.result_settings()
    assert s.stt.vad_speech_pad_ms == 450
    assert s.stt.log_prob_threshold == -0.8


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
    assert "temel URL" in dlg.error_label.text()
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
    assert "sunucu adresi" in dlg.error_label.text().lower()


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


def test_live_chunk_spin_defaults_and_round_trips(dlg):
    assert dlg.live_chunk_spin.value() == 20
    dlg.live_chunk_spin.setValue(0)
    s = dlg.result_settings()
    assert s.stt.live_chunk_s == 0


def test_profiles_starts_empty():
    d = SettingsDialog(Settings(), ())
    assert d.profiles_table.rowCount() == 0


def test_profiles_loads_existing_profiles():
    profile = AppProfile(name="Kod", match="code", mode="translate", paste="type")
    s = Settings(profiles=(profile,))
    d = SettingsDialog(s, ())
    assert d.profiles_table.rowCount() == 1
    assert d.profiles_table.item(0, 0).text() == "Kod"
    assert d.profiles_table.item(0, 1).text() == "code"


def test_profiles_round_trip(dlg):
    dlg.profiles.add_profile_btn.click()
    row = dlg.profiles_table.rowCount() - 1
    dlg.profiles_table.item(row, 0).setText("Terminal")
    dlg.profiles_table.item(row, 1).setText("windowsterminal")
    mode_combo = dlg.profiles_table.cellWidget(row, 2)
    mode_combo.setCurrentIndex(mode_combo.findData("prompt"))
    paste_combo = dlg.profiles_table.cellWidget(row, 3)
    paste_combo.setCurrentIndex(paste_combo.findData("ctrl+shift+v"))
    dlg.profiles_table.cellWidget(row, 4).setChecked(False)
    dlg.profiles_table.cellWidget(row, 5).setCurrentText("yeni satır")
    s = dlg.result_settings()
    assert s.profiles == (
        AppProfile(
            name="Terminal",
            match="windowsterminal",
            mode="prompt",
            paste="ctrl+shift+v",
            llm_enabled=False,
            trailing="\n",
        ),
    )


def test_profiles_rejects_empty_name_or_match(dlg):
    dlg.profiles.add_profile_btn.click()
    row = dlg.profiles_table.rowCount() - 1
    dlg.profiles_table.item(row, 1).setText("code")
    assert dlg.profiles.validate() == "Profilde ad ve eşleşme alanları boş olamaz"


def test_profiles_remove_selected(dlg):
    dlg.profiles.add_profile_btn.click()
    dlg.profiles_table.selectRow(0)
    dlg.profiles.remove_profile_btn.click()
    assert dlg.profiles_table.rowCount() == 0


# ---- yeni ayar alanları


def test_paste_last_hotkey_defaults_empty_and_round_trips(dlg):
    assert dlg.result_settings().hotkey_paste_last == ""
    dlg.hotkey_paste_last_edit.setKeySequence(QKeySequence("Ctrl+Alt+V"))
    assert dlg.result_settings().hotkey_paste_last == "ctrl+alt+v"


def test_paste_last_hotkey_loads_from_settings(qtbot):
    d = SettingsDialog(Settings(hotkey_paste_last="ctrl+alt+v"), ())
    qtbot.addWidget(d)
    assert d.hotkey_paste_last_edit.keySequence() == QKeySequence("Ctrl+Alt+V")


def test_paste_last_hotkey_must_differ_from_others(dlg):
    dlg.hotkey_paste_last_edit.setKeySequence(dlg.hotkey_edit.keySequence())
    dlg.accept()
    assert "farklı olmalı" in dlg.error_label.text()


def test_general_new_checks_round_trip(dlg):
    assert dlg.pause_media_check.isChecked() is False
    assert dlg.keep_failed_audio_check.isChecked() is True
    assert dlg.clipboard_exclude_history_check.isChecked() is True
    assert "Windows" in dlg.clipboard_exclude_history_check.toolTip()
    dlg.pause_media_check.setChecked(True)
    dlg.keep_failed_audio_check.setChecked(False)
    dlg.clipboard_exclude_history_check.setChecked(False)
    s = dlg.result_settings()
    assert (s.pause_media, s.keep_failed_audio, s.clipboard_exclude_history) == (
        True,
        False,
        False,
    )


def test_overlay_position_combo_shows_turkish_labels(dlg):
    combo = dlg.overlay_position_combo
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert labels == ["Altta", "Üstte", "Özel (sürüklenen yer)"]
    assert combo.currentData() == "bottom"
    combo.setCurrentIndex(combo.findData("top"))
    assert dlg.result_settings().overlay_position == "top"


def test_overlay_position_loads_and_keeps_xy(qtbot):
    d = SettingsDialog(Settings(overlay_position="custom", overlay_xy=(10, 20)), ())
    qtbot.addWidget(d)
    assert d.overlay_position_combo.currentData() == "custom"
    s = d.result_settings()
    assert s.overlay_position == "custom" and s.overlay_xy == (10, 20)


def test_history_retention_round_trip(dlg):
    assert dlg.history_retention_spin.value() == 0
    assert dlg.history_retention_spin.specialValueText() == "Sınırsız"
    dlg.history_retention_spin.setValue(30)
    assert dlg.result_settings().history_retention_days == 30


def test_history_spin_max_matches_config_clamp(dlg):
    from dikte.config import HISTORY_LIMIT_MAX

    assert dlg.history_spin.maximum() == HISTORY_LIMIT_MAX


def test_dead_mic_warning_round_trip(dlg):
    assert dlg.dead_mic_spin.value() == 3.0
    assert dlg.dead_mic_spin.specialValueText() == "Kapalı"
    dlg.dead_mic_spin.setValue(5.0)
    assert dlg.result_settings().audio.dead_mic_warn_s == 5.0


def test_llm_sanity_check_round_trip(dlg):
    assert dlg.sanity_check_check.isChecked() is True
    dlg.sanity_check_check.setChecked(False)
    assert dlg.result_settings().llm.sanity_check is False


# ---- varsayılanlara döndürme


def _non_default_settings() -> Settings:
    from dikte.config import AudioSettings, LlmSettings, SttSettings

    return Settings(
        hotkey="ctrl+shift+d",
        hotkey_translate="ctrl+alt+t",
        pause_media=True,
        overlay_position="top",
        history_retention_days=7,
        auto_copy=False,
        stt=SttSettings(
            vad_threshold=0.9,
            vad_min_silence_ms=3000,
            no_speech_threshold=0.2,
            log_prob_threshold=-3.0,
            batch_enabled=False,
            beam_size=2,
        ),
        llm=LlmSettings(provider="gemini", sanity_check=False, top_k=50, enabled=False),
        audio=AudioSettings(max_seconds=60, dead_mic_warn_s=0.0, device_name="USB Mic"),
    )


@pytest.fixture
def changed(qtbot):
    d = SettingsDialog(_non_default_settings(), ((0, "Mikrofon A"), (3, "USB Mic")))
    qtbot.addWidget(d)
    return d


@pytest.mark.parametrize("tab", ["general", "audio", "stt", "llm", "advanced"])
def test_each_settings_tab_has_reset_button(changed, tab):
    assert getattr(changed, tab).reset_btn.text() == "Varsayılanlara döndür"


def test_stt_reset_restores_thresholds_without_touching_other_tabs(changed):
    changed.stt.reset_btn.click()
    d = Settings().stt
    assert changed.vad_threshold_spin.value() == d.vad_threshold
    assert changed.vad_min_silence_spin.value() == d.vad_min_silence_ms
    assert changed.no_speech_spin.value() == d.no_speech_threshold
    assert changed.log_prob_spin.value() == d.log_prob_threshold
    assert changed.batch_check.isChecked() is True and changed.batch_size_spin.isEnabled()
    s = changed.result_settings()
    assert s.stt.vad_threshold == 0.5 and s.stt.batch_enabled is True
    assert s.stt.beam_size == 2  # Gelişmiş sekmesi etkilenmez
    assert s.pause_media is True and s.llm.provider == "gemini"


def test_general_reset_restores_defaults(changed):
    changed.general.reset_btn.click()
    s = changed.result_settings()
    default = Settings()
    assert s.hotkey == default.hotkey and s.hotkey_translate == ""
    assert s.pause_media is False and s.overlay_position == "bottom"
    assert s.history_retention_days == 0 and s.auto_copy is True
    assert changed.auto_paste_check.isEnabled()
    assert s.stt.vad_threshold == 0.9  # STT sekmesi etkilenmez


def test_audio_reset_restores_defaults(changed):
    changed.audio.reset_btn.click()
    s = changed.result_settings()
    assert s.audio.max_seconds == 0 and s.audio.dead_mic_warn_s == 3.0
    assert s.audio.device_name == "" and changed.device_combo.currentData() is None


def test_llm_reset_restores_defaults(changed):
    changed.llm.reset_btn.click()
    s = changed.result_settings()
    assert s.llm.provider == "ollama" and s.llm.sanity_check is True and s.llm.enabled
    assert changed.ollama_group.isVisibleTo(changed.llm)
    assert changed.provider_combo.isEnabled()
    assert s.llm.top_k == 50  # Gelişmiş sekmesi etkilenmez


def test_advanced_reset_restores_defaults(changed):
    changed.advanced.reset_btn.click()
    s = changed.result_settings()
    assert s.stt.beam_size == Settings().stt.beam_size and s.llm.top_k == 20
    assert s.stt.vad_threshold == 0.9


def test_reset_is_not_saved_until_result_settings(changed):
    original = changed._settings
    changed.stt.reset_btn.click()
    assert original.stt.vad_threshold == 0.9


# ---- arka plan işleri referansı


def test_connection_test_keeps_job_reference_until_done(dlg, monkeypatch):
    import dikte.ui.settings.llm_tab as llm_tab_mod

    class FakeProvider:
        def complete(self, system, user):
            return "OK"

    monkeypatch.setattr(llm_tab_mod, "make_provider", lambda settings: FakeProvider())
    pending = []
    job = object()

    def fake_run_in_pool(fn, on_result, on_error, pool=None):
        pending.append(on_result)
        return job

    monkeypatch.setattr(llm_tab_mod, "run_in_pool", fake_run_in_pool)
    dlg.llm_test_btn.click()
    assert dlg.llm._test_job is job
    assert dlg.llm_test_status.text() == "Sınanıyor…"
    pending[0]("OK")
    assert dlg.llm._test_job is None and "✓" in dlg.llm_test_status.text()


@pytest.mark.parametrize("outcome", ["result", "error"])
def test_connection_test_finishing_after_settings_closed_does_not_crash(
    qtbot, monkeypatch, outcome
):
    """Ayarlar test bitmeden kapanırsa (diyalog silinir) geç gelen sonuç silinmiş
    widget'lara dokunup RuntimeError fırlatmamalı."""
    from shiboken6 import Shiboken

    import dikte.ui.settings.llm_tab as llm_tab_mod

    class FakeProvider:
        def complete(self, system, user):
            return "OK"

    monkeypatch.setattr(llm_tab_mod, "make_provider", lambda settings: FakeProvider())
    callbacks = {}

    def fake_run_in_pool(fn, on_result, on_error, pool=None):
        callbacks.update(result=on_result, error=on_error)
        return object()

    monkeypatch.setattr(llm_tab_mod, "run_in_pool", fake_run_in_pool)
    tab = llm_tab_mod.LlmTab(Settings())
    tab.llm_test_btn.click()
    Shiboken.delete(tab)
    callbacks[outcome]("OK")  # RuntimeError fırlatmamalı


def test_about_probes_run_off_the_gui_thread(qtbot):
    import threading

    from dikte.ui.settings.about_tab import AboutTab

    threads = []

    def gpu():
        threads.append(threading.current_thread())
        return "sahte GPU"

    tab = AboutTab(Settings(), gpu_probe=gpu, vram_probe=lambda: "1 GB")
    qtbot.addWidget(tab)
    assert tab._probe_job is not None
    qtbot.waitUntil(lambda: tab.gpu_label.text() == "sahte GPU", timeout=3000)
    assert tab.vram_label.text() == "1 GB"
    assert threads and threads[0] is not threading.main_thread()
    assert tab._probe_job is None


def test_about_probe_failure_shows_unknown(qtbot):
    from dikte.ui.settings.about_tab import AboutTab

    def boom():
        raise RuntimeError("nvidia-smi yok")

    tab = AboutTab(Settings(), gpu_probe=boom, vram_probe=lambda: "1 GB")
    qtbot.addWidget(tab)
    qtbot.waitUntil(lambda: tab._probe_job is None, timeout=3000)
    assert tab.gpu_label.text() == "bilinmiyor" and tab.vram_label.text() == "bilinmiyor"


# ---- Türkçe etiketler


def test_profile_combos_show_turkish_labels_with_raw_data(qtbot):
    profile = AppProfile(name="Kod", match="code", mode="translate", paste="type")
    d = SettingsDialog(Settings(profiles=(profile,)), ())
    qtbot.addWidget(d)
    mode_combo = d.profiles_table.cellWidget(0, 2)
    paste_combo = d.profiles_table.cellWidget(0, 3)
    modes = [mode_combo.itemText(i) for i in range(mode_combo.count())]
    assert "correct" not in modes and "translate" not in modes
    assert mode_combo.currentData() == "translate"
    assert paste_combo.currentData() == "type" and paste_combo.currentText() != "type"
    assert d.result_settings().profiles == (profile,)


def test_llm_form_labels_are_turkish(dlg):
    from PySide6.QtWidgets import QLabel

    texts = {label.text() for label in dlg.llm.findChildren(QLabel)}
    assert not texts & {"Host", "Base URL", "Format"}
    assert {"Sunucu adresi", "Temel URL", "Biçim"} <= texts
    combo = dlg.custom_format_combo
    assert [combo.itemData(i) for i in range(combo.count())] == ["openai", "anthropic"]


def test_ineffective_hallucination_silence_control_is_hidden_but_value_kept(qtbot):
    from dikte.config import SttSettings

    d = SettingsDialog(Settings(stt=SttSettings(hallucination_silence_threshold_s=4.5)), ())
    qtbot.addWidget(d)
    assert not hasattr(d.stt, "hallucination_silence_spin")
    assert d.result_settings().stt.hallucination_silence_threshold_s == 4.5


def test_about_tab_health_button_requests_app_health_dialog(qtbot):
    """Durum penceresini sekme değil uygulama açar: indirilen model yüklenir ve pencere
    ayarlar diyaloğu silinince (deleteLater) onunla birlikte yok olmaz."""
    from dikte.ui.settings.about_tab import AboutTab

    tab = AboutTab(Settings(), gpu_probe=lambda: "g", vram_probe=lambda: "v")
    qtbot.addWidget(tab)
    with qtbot.waitSignal(tab.health_requested, timeout=1000):
        tab.health_btn.click()


def test_settings_dialog_forwards_health_request(dlg, qtbot):
    with qtbot.waitSignal(dlg.health_requested, timeout=1000):
        dlg.health_btn.click()
