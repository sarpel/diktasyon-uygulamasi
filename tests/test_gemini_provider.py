from types import SimpleNamespace

import pytest

from dikte.config import LlmSettings
from dikte.llm.gemini_provider import GeminiProvider
from dikte.llm.provider import LlmError


class FakeGenai:
    def __init__(self, text="ok", fail=None):
        self.text, self.fail, self.calls = text, fail, []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise self.fail
        return SimpleNamespace(text=self.text)


def make(monkeypatch, fake, **settings_kwargs):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    return GeminiProvider(
        LlmSettings(**settings_kwargs), client_factory=lambda api_key, timeout_s: fake
    )


def test_schema_goes_to_response_json_schema(monkeypatch):
    fake = FakeGenai('{"a": 1}')
    p = make(monkeypatch, fake, gemini_model="g")
    p.complete("sys", "usr", json_schema={"type": "object"}, temperature=0.1)
    call = fake.calls[-1]
    cfg = call["config"]
    assert call["model"] == "g" and call["contents"] == "usr"
    assert cfg["system_instruction"] == "sys" and cfg["response_mime_type"] == "application/json"
    assert cfg["response_json_schema"] == {"type": "object"} and cfg["temperature"] == 0.1


def test_plain_text_when_no_schema(monkeypatch):
    fake = FakeGenai("merhaba")
    assert make(monkeypatch, fake).complete("s", "u") == "merhaba"
    assert "response_mime_type" not in fake.calls[-1]["config"]


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LlmError, match="GEMINI_API_KEY"):
        GeminiProvider(LlmSettings(), client_factory=lambda api_key, timeout_s: FakeGenai())


def test_custom_key_env_name_is_used(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("MY_KEY", "v")
    seen = {}
    GeminiProvider(
        LlmSettings(gemini_api_key_env="MY_KEY"),
        client_factory=lambda api_key, timeout_s: seen.setdefault("key", api_key) and FakeGenai(),
    )
    assert seen["key"] == "v"


def test_empty_response_raises(monkeypatch):
    with pytest.raises(LlmError, match="boş yanıt"):
        make(monkeypatch, FakeGenai("")).complete("s", "u")


def test_api_failure_wrapped(monkeypatch):
    with pytest.raises(LlmError, match="Gemini"):
        make(monkeypatch, FakeGenai(fail=RuntimeError("429"))).complete("s", "u")


def test_timeout_is_forwarded_to_client_factory(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    captured = {}

    def factory(api_key, timeout_s):
        captured["api_key"], captured["timeout_s"] = api_key, timeout_s
        return FakeGenai()

    GeminiProvider(LlmSettings(timeout_s=42.0), client_factory=factory)
    assert captured == {"api_key": "k", "timeout_s": 42.0}


@pytest.mark.parametrize("reason", ["MAX_TOKENS", SimpleNamespace(name="MAX_TOKENS")])
def test_max_tokens_finish_reason_raises_truncation_error(monkeypatch, reason):
    fake = FakeGenai("yarım")
    fake.generate_content = lambda **kw: SimpleNamespace(
        text="yarım", candidates=[SimpleNamespace(finish_reason=reason)]
    )
    with pytest.raises(LlmError, match="yarıda kesildi"):
        make(monkeypatch, fake).complete("s", "u")
