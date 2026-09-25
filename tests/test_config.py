from pathlib import Path

import pytest

from dikte.config import Settings, load_settings, save_settings


def test_default_settings_values():
    s = Settings()
    assert s.hotkey == "ctrl+alt+space"
    assert s.stt.model == "large-v3-turbo"
    assert s.stt.language == "tr"
    assert s.llm.provider == "ollama"
    assert s.llm.model == "gemma4:e4b-it-qat"
    assert s.llm.think is False


def test_settings_are_immutable():
    s = Settings()
    with pytest.raises(Exception):
        s.hotkey = "ctrl+shift+d"  # type: ignore[misc]


def test_save_and_load_roundtrip(tmp_path: Path):
    p = tmp_path / "config.json"
    s = Settings().model_copy(update={"hotkey": "ctrl+shift+d"})
    save_settings(s, p)
    assert load_settings(p) == s


def test_load_missing_file_returns_defaults(tmp_path: Path):
    assert load_settings(tmp_path / "nope.json") == Settings()


def test_load_corrupt_file_returns_defaults_and_backs_up(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_settings(p) == Settings()
    assert (tmp_path / "config.json.bak").exists()


def test_default_recording_is_unlimited():
    from dikte.config import AudioSettings

    assert AudioSettings().max_seconds == 0


def test_negative_max_seconds_rejected():
    from pydantic import ValidationError

    from dikte.config import AudioSettings

    with pytest.raises(ValidationError):
        AudioSettings(max_seconds=-1)


def test_result_delivery_defaults():
    s = Settings()
    assert s.auto_copy is True and s.auto_paste is True and s.raise_window_on_result is False


def test_llm_provider_options_include_remote_and_custom():
    from dikte.config import LlmSettings

    for provider in ("ollama", "openai", "anthropic", "gemini", "custom"):
        assert LlmSettings(provider=provider).provider == provider


def test_unknown_llm_provider_rejected():
    from pydantic import ValidationError

    from dikte.config import LlmSettings

    with pytest.raises(ValidationError):
        LlmSettings(provider="mistral")  # pyright: ignore[reportArgumentType]  # kasıtlı geçersiz


def test_custom_format_defaults_to_openai_and_key_env_is_empty():
    from dikte.config import LlmSettings

    s = LlmSettings()
    assert s.custom_format == "openai" and s.custom_api_key_env == ""


def test_old_config_without_new_llm_fields_still_loads(tmp_path: Path):
    import json

    p = tmp_path / "config.json"
    p.write_text(
        json.dumps({"llm": {"provider": "ollama", "model": "qwen3.5:4b"}}), encoding="utf-8"
    )
    loaded = load_settings(p)
    assert loaded.llm.gemini_model and loaded.llm.custom_base_url == ""


def test_dictionary_defaults_to_empty_and_loads_from_json():
    assert Settings().dictionary.entries == ()
    loaded = Settings.model_validate_json('{"dictionary": {"entries": [{"term": "X"}]}}')
    assert loaded.dictionary.entries[0].term == "X"
    assert loaded.dictionary.entries[0].wrong == ()


def test_local_server_defaults_match_vendor_ports():
    from dikte.config import LlmSettings

    llm = LlmSettings()
    assert llm.ollama_host == "http://127.0.0.1:11434"
    assert llm.lmstudio_base_url == "http://127.0.0.1:1234/v1"
    assert llm.lmstudio_model == "" and llm.lmstudio_api_key_env == ""


def test_ollama_host_is_configurable():
    from dikte.config import LlmSettings

    llm = LlmSettings().model_copy(update={"ollama_host": "http://127.0.0.1:11500"})
    assert llm.ollama_host == "http://127.0.0.1:11500"


def test_active_model_follows_provider():
    from dikte.config import LlmSettings

    base = LlmSettings(lmstudio_model="lm-4b", custom_model="öz-model")
    assert base.active_model == "gemma4:e4b-it-qat"
    assert base.model_copy(update={"provider": "lmstudio"}).active_model == "lm-4b"
    # Model adları sürüm çıktıkça değişir; test eşlemeyi doğrular, sabit adı değil.
    assert base.model_copy(update={"provider": "openai"}).active_model == base.openai_model
    assert base.model_copy(update={"provider": "gemini"}).active_model == base.gemini_model
    assert base.model_copy(update={"provider": "custom"}).active_model == "öz-model"


def test_profiles_default_to_empty():
    assert Settings().profiles == ()


def test_app_profile_defaults():
    from dikte.config import AppProfile

    p = AppProfile(name="Kod", match="code")
    assert p.mode == "correct"
    assert p.paste == "ctrl+v"
    assert p.llm_enabled is True
    assert p.trailing == ""


def test_app_profile_is_immutable():
    from dikte.config import AppProfile

    p = AppProfile(name="Kod", match="code")
    with pytest.raises(Exception):
        p.name = "x"  # type: ignore[misc]


def test_profiles_load_from_json():
    loaded = Settings.model_validate_json(
        '{"profiles": [{"name": "Terminal", "match": "windowsterminal", '
        '"paste": "ctrl+shift+v", "llm_enabled": false}]}'
    )
    assert loaded.profiles[0].name == "Terminal"
    assert loaded.profiles[0].paste == "ctrl+shift+v"
    assert loaded.profiles[0].llm_enabled is False


def test_old_config_without_profiles_still_loads(tmp_path: Path):
    import json

    p = tmp_path / "config.json"
    p.write_text(json.dumps({"hotkey": "ctrl+alt+space"}), encoding="utf-8")
    assert load_settings(p).profiles == ()


def test_live_chunk_defaults():
    s = Settings()
    assert s.stt.live_chunk_s == 20.0
    assert s.stt.live_max_chunk_s == 45.0


def test_live_chunk_s_zero_allowed():
    from dikte.config import SttSettings

    assert SttSettings(live_chunk_s=0).live_chunk_s == 0


def test_live_chunk_s_negative_rejected():
    from dikte.config import SttSettings

    with pytest.raises(Exception):
        SttSettings(live_chunk_s=-1)


def test_live_max_chunk_s_below_five_rejected():
    from dikte.config import SttSettings

    with pytest.raises(Exception):
        SttSettings(live_max_chunk_s=4)


# ---- bozuk ayar kurtarma: tek hatalı alan tüm ayarları sıfırlamamalı


def test_one_invalid_field_keeps_the_rest(tmp_path: Path):
    import json

    from dikte.config import load_settings_with_issues

    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "hotkey": "ctrl+shift+d",
                "stt": {"beam_size": 99, "model": "small"},
                "llm": {"provider": "gelecekteki-saglayici", "model": "qwen"},
            }
        ),
        encoding="utf-8",
    )
    s, issues = load_settings_with_issues(p)
    assert s.hotkey == "ctrl+shift+d"
    assert s.stt.model == "small" and s.stt.beam_size == 5
    assert s.llm.model == "qwen" and s.llm.provider == "ollama"
    assert set(issues) == {"stt.beam_size", "llm.provider"}
    assert (tmp_path / "config.json.bak").exists()


def test_invalid_profile_entry_drops_only_profiles(tmp_path: Path):
    import json

    from dikte.config import load_settings_with_issues

    p = tmp_path / "config.json"
    p.write_text(json.dumps({"hotkey": "f9", "profiles": [{"name": "x"}]}), encoding="utf-8")
    s, issues = load_settings_with_issues(p)
    assert s.hotkey == "f9" and s.profiles == ()
    assert issues == ("profiles",)


def test_non_json_file_reports_whole_file(tmp_path: Path):
    from dikte.config import load_settings_with_issues

    p = tmp_path / "config.json"
    p.write_text("{bozuk", encoding="utf-8")
    s, issues = load_settings_with_issues(p)
    assert s == Settings() and issues == ("*",)


def test_valid_file_has_no_issues(tmp_path: Path):
    from dikte.config import load_settings_with_issues

    p = tmp_path / "config.json"
    save_settings(Settings(hotkey="f8"), p)
    s, issues = load_settings_with_issues(p)
    assert s.hotkey == "f8" and issues == ()
    assert not (tmp_path / "config.json.bak").exists()


def test_history_limit_is_clamped_not_rejected():
    assert Settings(history_limit=999_999).history_limit == 5000


def test_new_qol_defaults():
    s = Settings()
    assert s.hotkey_paste_last == ""
    assert s.pause_media is False
    assert s.keep_failed_audio is True
    assert s.overlay_position == "bottom" and s.overlay_xy is None
    assert s.history_retention_days == 0
    assert s.clipboard_exclude_history is True
    assert s.audio.device_name == "" and s.audio.dead_mic_warn_s == 3.0
    assert s.llm.sanity_check is True


def test_old_config_with_device_index_only_still_loads(tmp_path: Path):
    import json

    p = tmp_path / "config.json"
    p.write_text(json.dumps({"audio": {"device_index": 3}}), encoding="utf-8")
    s = load_settings(p)
    assert s.audio.device_index == 3 and s.audio.device_name == ""
