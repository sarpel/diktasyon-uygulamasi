from types import SimpleNamespace

import pytest

from dikte.config import LlmSettings
from dikte.llm.openai_provider import OpenAiCompatProvider, _schema_unsupported_errors
from dikte.llm.provider import LlmError


class FakeCompletions:
    def __init__(self, reply="ok", reject_schema=False, fail=None):
        self.reply, self.reject_schema, self.fail = reply, reject_schema, fail
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise self.fail
        if self.reject_schema and kwargs.get("response_format", {}).get("type") == "json_schema":
            raise ValueError("json_schema desteklenmiyor")
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.completions = FakeCompletions(**kwargs.pop("behaviour", {}))
        self.chat = SimpleNamespace(completions=self.completions)

    @property
    def calls(self):
        return self.completions.calls


def make(fake, **overrides):
    options = {
        "base_url": "http://x/v1",
        "model": "m",
        "api_key_env": "",
        "required_key": False,
    }
    options.update(overrides)
    return OpenAiCompatProvider(LlmSettings(), client_factory=lambda **k: fake, **options)


def test_json_schema_passed_as_response_format():
    fake = FakeOpenAI(behaviour={"reply": "{}"})
    make(fake).complete("s", "u", json_schema={"type": "object"})
    rf = fake.calls[-1]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["schema"] == {"type": "object"}


def test_falls_back_to_json_object_when_schema_rejected():
    fake = FakeOpenAI(behaviour={"reply": '{"a": 1}', "reject_schema": True})
    out = make(fake).complete("s", "u", json_schema={"type": "object"})
    assert fake.calls[-1]["response_format"] == {"type": "json_object"}
    assert "JSON object matching this schema" in fake.calls[-1]["messages"][0]["content"]
    assert out.startswith("{")


def test_schema_fallback_covers_builtin_errors_regardless_of_sdk():
    # openai SDK kurulu olsun olmasın yerleşik hatalar yakalanmalı (CI'de SDK kuruludur).
    assert set(_schema_unsupported_errors()) >= {ValueError, TypeError}


def test_plain_request_has_no_response_format():
    fake = FakeOpenAI(behaviour={"reply": "merhaba"})
    assert make(fake).complete("s", "u") == "merhaba"
    assert "response_format" not in fake.calls[-1]


def test_missing_required_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LlmError, match="OPENAI_API_KEY"):
        OpenAiCompatProvider(
            LlmSettings(),
            base_url="https://api.openai.com/v1",
            model="m",
            api_key_env="OPENAI_API_KEY",
            required_key=True,
            client_factory=lambda **k: FakeOpenAI(),
        )


def test_base_url_and_timeout_forwarded_to_client():
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return FakeOpenAI()

    OpenAiCompatProvider(
        LlmSettings(timeout_s=42.0),
        base_url="http://localhost:1234/v1",
        model="m",
        api_key_env="",
        required_key=False,
        client_factory=factory,
    )
    assert captured["base_url"] == "http://localhost:1234/v1" and captured["timeout"] == 42.0
    assert captured["api_key"] is None


def test_network_error_wrapped():
    fake = FakeOpenAI(behaviour={"fail": ConnectionError("down")})
    with pytest.raises(LlmError, match="OpenAI-uyumlu"):
        make(fake).complete("s", "u")


def test_empty_reply_raises():
    fake = FakeOpenAI(behaviour={"reply": "   "})
    with pytest.raises(LlmError, match="boş yanıt"):
        make(fake).complete("s", "u")


def test_custom_name_is_reported():
    assert make(FakeOpenAI(), name="custom-openai").name == "custom-openai"


def _truncated_response(content="yarım"):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="length")])


def test_length_finish_reason_raises_truncation_error():
    fake = FakeOpenAI(behaviour={})
    fake.completions.create = lambda **kw: _truncated_response()
    with pytest.raises(LlmError, match="yarıda kesildi"):
        make(fake).complete("s", "u")


def test_length_finish_reason_raises_for_json_too():
    fake = FakeOpenAI(behaviour={})
    fake.completions.create = lambda **kw: _truncated_response('{"corrected_text": "ya')
    with pytest.raises(LlmError, match="yarıda kesildi"):
        make(fake).complete("s", "u", json_schema={"type": "object"})


# ---- json_schema geri dönüşü yalnızca response_format reddinde


class _RejectingCompletions(FakeCompletions):
    """json_schema isteğinde verilen hatayı fırlatır, diğer isteklerde yanıt döndürür."""

    def __init__(self, error):
        super().__init__(reply='{"a": 1}')
        self.error = error

    def create(self, **kwargs):
        if kwargs.get("response_format", {}).get("type") == "json_schema":
            self.calls.append(kwargs)
            raise self.error
        return super().create(**kwargs)


def _bad_request(message, body):
    openai = pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")
    response = httpx.Response(400, request=httpx.Request("POST", "http://x/v1"))
    return openai.BadRequestError(message, response=response, body=body)


def _provider_raising(error):
    fake = FakeOpenAI()
    fake.completions = _RejectingCompletions(error)
    fake.chat = SimpleNamespace(completions=fake.completions)
    return fake, make(fake)


@pytest.mark.parametrize(
    ("message", "body"),
    [
        ("Error code: 400", {"message": "invalid value", "param": "response_format"}),
        ("Error code: 400 - 'json_schema' is not supported by this model", None),
        ("Error code: 400", {"error": {"message": "response_format.type unsupported"}}),
    ],
)
def test_bad_request_about_response_format_falls_back(message, body):
    fake, provider = _provider_raising(_bad_request(message, body))
    assert provider.complete("s", "u", json_schema={"type": "object"}).startswith("{")
    assert fake.calls[-1]["response_format"] == {"type": "json_object"}


def test_unrelated_bad_request_is_not_retried_with_json_object():
    error = _bad_request(
        "Error code: 400 - context length exceeded",
        {"message": "maximum context length exceeded", "param": "messages", "code": "ctx"},
    )
    fake, provider = _provider_raising(error)
    with pytest.raises(LlmError, match="OpenAI-uyumlu"):
        provider.complete("s", "u", json_schema={"type": "object"})
    assert len(fake.calls) == 1
