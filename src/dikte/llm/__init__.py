from dikte.config import LlmSettings
from dikte.llm.provider import LlmError, LlmProvider


def _custom_provider(settings: LlmSettings) -> LlmProvider:
    if not settings.custom_base_url.strip() or not settings.custom_model.strip():
        raise LlmError("Özel sağlayıcı için base URL ve model adı gerekli")
    if settings.custom_format == "openai":
        from dikte.llm.openai_provider import OpenAiCompatProvider

        return OpenAiCompatProvider(
            settings,
            base_url=settings.custom_base_url.strip(),
            model=settings.custom_model.strip(),
            api_key_env=settings.custom_api_key_env,
            required_key=False,  # yerel sunucular anahtar istemeyebilir
            name="custom-openai",
        )
    from dikte.llm.anthropic_provider import AnthropicProvider

    return AnthropicProvider(
        settings,
        base_url=settings.custom_base_url.strip(),
        model=settings.custom_model.strip(),
        api_key_env=settings.custom_api_key_env,
        required_key=False,
        name="custom-anthropic",
    )


def make_provider(settings: LlmSettings) -> LlmProvider:
    provider = settings.provider
    if provider == "ollama":
        from dikte.llm.ollama_provider import OllamaProvider

        return OllamaProvider(settings)
    if provider == "openai":
        from dikte.llm.openai_provider import OpenAiCompatProvider

        return OpenAiCompatProvider(
            settings,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            api_key_env=settings.openai_api_key_env,
            required_key=True,
        )
    if provider == "anthropic":
        from dikte.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings, api_key_env=settings.anthropic_api_key_env)
    if provider == "gemini":
        from dikte.llm.gemini_provider import GeminiProvider

        return GeminiProvider(settings)
    if provider == "custom":
        return _custom_provider(settings)
    raise LlmError(f"Bilinmeyen LLM sağlayıcı: {provider}")


__all__ = ["LlmError", "LlmProvider", "make_provider"]
