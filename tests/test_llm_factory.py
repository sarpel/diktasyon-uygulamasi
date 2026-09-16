import pytest

from dikte.config import LlmSettings
from dikte.llm import make_provider
from dikte.llm.provider import LlmError


@pytest.fixture
def stub_sdks(monkeypatch):
    """Gerçek SDK'lar kurulu olmadan fabrikanın dallarını sınar."""
    from types import SimpleNamespace

    import dikte.llm.anthropic_provider as anthropic_mod
    import dikte.llm.gemini_provider as gemini_mod
    import dikte.llm.openai_provider as openai_mod

    monkeypatch.setattr(
        openai_mod, "_default_client_factory", lambda **k: SimpleNamespace(chat=None)
    )
    monkeypatch.setattr(
        anthropic_mod, "_default_client_factory", lambda *a, **k: SimpleNamespace(messages=None)
    )
    monkeypatch.setattr(gemini_mod, "_default_client_factory", lambda api_key: SimpleNamespace())
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")


@pytest.mark.parametrize(
    ("provider", "expected"),
    [("ollama", "ollama"), ("openai", "openai"), ("anthropic", "anthropic"), ("gemini", "gemini")],
)
def test_factory_builds_named_provider(provider, expected, stub_sdks):
    assert make_provider(LlmSettings(provider=provider)).name == expected


def test_custom_openai_format(stub_sdks):
    s = LlmSettings(
        provider="custom", custom_format="openai", custom_base_url="http://h/v1", custom_model="m"
    )
    assert make_provider(s).name == "custom-openai"


def test_custom_anthropic_format(stub_sdks):
    s = LlmSettings(
        provider="custom", custom_format="anthropic", custom_base_url="http://h", custom_model="m"
    )
    assert make_provider(s).name == "custom-anthropic"


def test_custom_requires_url_and_model():
    with pytest.raises(LlmError, match="base URL"):
        make_provider(LlmSettings(provider="custom"))


def test_custom_requires_model_when_url_given():
    with pytest.raises(LlmError, match="base URL"):
        make_provider(LlmSettings(provider="custom", custom_base_url="http://h/v1"))


def test_custom_works_without_api_key(monkeypatch, stub_sdks):
    monkeypatch.delenv("LOCAL_KEY", raising=False)
    s = LlmSettings(
        provider="custom",
        custom_base_url="http://h/v1",
        custom_model="m",
        custom_api_key_env="LOCAL_KEY",
    )
    assert make_provider(s).name == "custom-openai"


def test_missing_openai_sdk_gives_install_hint(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("yok")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    with pytest.raises(LlmError, match=r"\[openai\]"):
        make_provider(LlmSettings(provider="openai"))


def test_missing_gemini_sdk_gives_install_hint(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("google"):
            raise ImportError("yok")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    with pytest.raises(LlmError, match=r"\[gemini\]"):
        make_provider(LlmSettings(provider="gemini"))


def test_lmstudio_provider_is_openai_compatible(stub_sdks):
    s = LlmSettings(provider="lmstudio", lmstudio_model="qwen3.5-4b")
    assert make_provider(s).name == "lmstudio"


def test_lmstudio_requires_model():
    with pytest.raises(LlmError, match="model adı"):
        make_provider(LlmSettings(provider="lmstudio"))


def test_lmstudio_works_without_api_key(monkeypatch, stub_sdks):
    monkeypatch.delenv("LMSTUDIO_API_KEY", raising=False)
    s = LlmSettings(
        provider="lmstudio", lmstudio_model="m", lmstudio_api_key_env="LMSTUDIO_API_KEY"
    )
    assert make_provider(s).name == "lmstudio"
