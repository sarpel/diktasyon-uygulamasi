import pytest

from dikte.llm.keys import key_status, read_api_key
from dikte.llm.provider import LlmError


def test_required_key_missing_raises(monkeypatch):
    monkeypatch.delenv("X_KEY", raising=False)
    with pytest.raises(LlmError, match="X_KEY"):
        read_api_key("X_KEY", required=True)


def test_optional_key_missing_returns_none(monkeypatch):
    monkeypatch.delenv("X_KEY", raising=False)
    assert read_api_key("X_KEY", required=False) is None


def test_empty_env_name_means_no_key():
    assert read_api_key("", required=False) is None


def test_empty_env_name_with_required_raises():
    with pytest.raises(LlmError):
        read_api_key("", required=True)


def test_key_is_returned_when_set(monkeypatch):
    monkeypatch.setenv("X_KEY", "gizli")
    assert read_api_key("X_KEY", required=True) == "gizli"


def test_whitespace_only_key_counts_as_missing(monkeypatch):
    monkeypatch.setenv("X_KEY", "   ")
    assert read_api_key("X_KEY", required=False) is None


def test_key_status_never_exposes_value(monkeypatch):
    monkeypatch.setenv("X_KEY", "gizli")
    assert key_status("X_KEY") is True
    monkeypatch.delenv("X_KEY")
    assert key_status("X_KEY") is False


def test_key_status_is_false_for_empty_name():
    assert key_status("") is False
