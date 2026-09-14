from types import SimpleNamespace

import pytest

from dikte.config import LlmSettings
from dikte.llm.anthropic_provider import AnthropicProvider
from dikte.llm.provider import LlmError


class FakeMessages:
    def __init__(self, blocks, fail=None):
        self.blocks, self.fail, self.calls = blocks, fail, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise self.fail
        return SimpleNamespace(content=self.blocks)


class FakeClient:
    def __init__(self, blocks, fail=None):
        self.messages = FakeMessages(blocks, fail)


def make(monkeypatch, blocks, fail=None):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = FakeClient(blocks, fail)
    provider = AnthropicProvider(LlmSettings(provider="anthropic"), lambda key, timeout: client)
    return provider, client


def test_complete_joins_text_blocks(monkeypatch):
    p, c = make(monkeypatch, [SimpleNamespace(text="Hello "), SimpleNamespace(text="world.")])
    assert p.complete("SYS", "USER") == "Hello world."
    call = c.messages.calls[0]
    assert call["model"] == "claude-sonnet-5" and call["system"] == "SYS"
    assert call["messages"] == [{"role": "user", "content": "USER"}]


def test_json_schema_is_appended_to_system_and_output_is_trimmed(monkeypatch):
    p, c = make(monkeypatch, [SimpleNamespace(text='Tabii: {"a": 1} umarım olur')])
    out = p.complete("SYS", "USER", json_schema={"type": "object"})
    assert out == '{"a": 1}'
    assert "JSON object matching this schema" in c.messages.calls[0]["system"]


def test_api_failure_becomes_llm_error(monkeypatch):
    p, _ = make(monkeypatch, [], fail=RuntimeError("429"))
    with pytest.raises(LlmError, match="Anthropic"):
        p.complete("s", "u")


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LlmError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(LlmSettings(provider="anthropic"), lambda key, timeout: None)
