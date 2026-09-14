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
