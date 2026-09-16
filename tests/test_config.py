from pathlib import Path

import pytest

from dikte.config import Settings, load_settings, save_settings


def test_default_settings_values():
    s = Settings()
    assert s.hotkey == "ctrl+alt+space"
    assert s.stt.model == "large-v3-turbo"
    assert s.stt.language == "tr"
    assert s.llm.provider == "ollama"
    assert s.llm.model == "qwen3.5:4b"
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
        LlmSettings(provider="mistral")


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
    assert base.active_model == "qwen3.5:4b"
    assert base.model_copy(update={"provider": "lmstudio"}).active_model == "lm-4b"
    assert base.model_copy(update={"provider": "openai"}).active_model == "gpt-5.5"
    assert base.model_copy(update={"provider": "gemini"}).active_model == "gemini-3.5-flash"
    assert base.model_copy(update={"provider": "custom"}).active_model == "öz-model"
