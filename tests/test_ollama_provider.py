from types import SimpleNamespace

import pytest

from dikte.config import LlmSettings
from dikte.llm import make_provider
from dikte.llm.ollama_provider import OllamaProvider, estimate_num_ctx
from dikte.llm.provider import LlmError


class FakeClient:
    def __init__(self, reply="ok", fail=None):
        self.reply, self.fail, self.calls = reply, fail, []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise self.fail
        return SimpleNamespace(message=SimpleNamespace(content=self.reply))


def test_complete_sends_system_and_user_messages():
    c = FakeClient("cevap")
    p = OllamaProvider(LlmSettings(), client_factory=lambda host, timeout: c)
    assert p.complete("SYS", "USER") == "cevap"
    call = c.calls[0]
    assert call["model"] == "gemma4:e4b-it-qat"
    assert call["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]
    assert call["keep_alive"] == "30m" and call["options"]["temperature"] == 0.2
    assert call["think"] is False and call["options"]["num_ctx"] == 8192
    assert "format" not in call or call["format"] is None


def test_complete_passes_json_schema_as_format():
    c = FakeClient("{}")
    p = OllamaProvider(LlmSettings(), client_factory=lambda host, timeout: c)
    p.complete("s", "u", json_schema={"type": "object"})
    assert c.calls[0]["format"] == {"type": "object"}


def test_connection_error_becomes_llm_error():
    c = FakeClient(fail=ConnectionError("refused"))
    p = OllamaProvider(LlmSettings(), client_factory=lambda host, timeout: c)
    with pytest.raises(LlmError, match="Ollama"):
        p.complete("s", "u")


def test_make_provider_selects_ollama_by_default():
    assert make_provider(LlmSettings()).name == "ollama"


def test_make_provider_anthropic_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LlmError, match="ANTHROPIC_API_KEY"):
        make_provider(LlmSettings(provider="anthropic"))


def test_warm_up_sends_empty_chat_with_keep_alive():
    c = FakeClient()
    p = OllamaProvider(
        LlmSettings(model="m", keep_alive="30m"), client_factory=lambda host, timeout: c
    )
    p.warm_up()
    call = c.calls[-1]
    assert call["model"] == "m" and call["messages"] == [] and call["keep_alive"] == "30m"


def test_warm_up_error_is_logged_not_raised(caplog):
    c = FakeClient(fail=ConnectionError("refused"))
    p = OllamaProvider(LlmSettings(), client_factory=lambda host, timeout: c)
    p.warm_up()
    assert "ısındırma" in caplog.text.lower()


def test_unload_requests_zero_keep_alive():
    client = FakeClient()
    provider = OllamaProvider(LlmSettings(model="m"), client_factory=lambda host, timeout: client)
    provider.unload()
    assert client.calls[-1]["keep_alive"] == 0 and client.calls[-1]["model"] == "m"


def test_length_done_reason_raises_truncation_error():
    c = FakeClient("yarım")
    c.chat = lambda **kw: SimpleNamespace(
        message=SimpleNamespace(content="yarım"), done_reason="length"
    )
    p = OllamaProvider(LlmSettings(), client_factory=lambda host, timeout: c)
    with pytest.raises(LlmError, match="yarıda kesildi"):
        p.complete("s", "u")


def test_num_ctx_grows_with_long_input():
    c = FakeClient("ok")
    p = OllamaProvider(LlmSettings(), client_factory=lambda host, timeout: c)
    p.complete("s", "a" * 30_000)
    assert c.calls[0]["options"]["num_ctx"] > 8192


def test_estimate_num_ctx_keeps_base_for_short_text():
    assert estimate_num_ctx("sistem", "kısa metin", base=8192) == 8192


def test_estimate_num_ctx_rounds_up_to_2048_multiple():
    # (3000 + 12000) / 3 = 5000 giriş + 12000/3*2 = 8000 çıkış → 13000 → 14336
    assert estimate_num_ctx("s" * 3000, "u" * 12000, base=8192) == 14336


def test_estimate_num_ctx_caps_at_32768():
    assert estimate_num_ctx("s", "u" * 200_000, base=8192) == 32768


def test_estimate_num_ctx_respects_larger_base():
    assert estimate_num_ctx("s", "u" * 200_000, base=65536) == 65536
