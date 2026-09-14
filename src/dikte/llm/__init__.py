from dikte.config import LlmSettings
from dikte.llm.provider import LlmError, LlmProvider


def make_provider(settings: LlmSettings) -> LlmProvider:
    if settings.provider == "ollama":
        from dikte.llm.ollama_provider import OllamaProvider

        return OllamaProvider(settings)
    if settings.provider == "anthropic":
        from dikte.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings)
    raise LlmError(f"Bilinmeyen LLM sağlayıcı: {settings.provider}")


__all__ = ["LlmError", "LlmProvider", "make_provider"]
