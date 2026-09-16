"""Google Gemini (google-genai SDK) sağlayıcısı."""

from __future__ import annotations

import logging
from collections.abc import Callable

from dikte.config import LlmSettings
from dikte.llm.keys import read_api_key
from dikte.llm.provider import LlmError

log = logging.getLogger(__name__)


def _default_client_factory(api_key: str):
    try:
        from google import genai
    except ImportError as exc:
        raise LlmError('Gemini SDK kurulu değil: uv pip install -e ".[gemini]"') from exc
    return _GenaiAdapter(genai.Client(api_key=api_key))


class _GenaiAdapter:
    """Sağlayıcı config'i dict olarak üretir; gerçek SDK'da types nesnesine sarılır."""

    def __init__(self, client):
        self._client = client

    def generate_content(self, *, model: str, contents: str, config: dict):
        from google.genai import types

        return self._client.models.generate_content(
            model=model, contents=contents, config=types.GenerateContentConfig(**config)
        )


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: LlmSettings, client_factory: Callable | None = None):
        self._settings = settings
        api_key = read_api_key(settings.gemini_api_key_env, required=True)
        self._client = (client_factory or _default_client_factory)(api_key)

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict | None = None,
        temperature: float = 0.2,
    ) -> str:
        config: dict = {
            "system_instruction": system,
            "temperature": temperature,
            "top_p": self._settings.top_p,
        }
        if json_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = json_schema
        try:
            response = self._client.generate_content(
                model=self._settings.gemini_model, contents=user, config=config
            )
        except LlmError:
            raise
        except Exception as exc:  # SDK hata sınıfları isteğe bağlı bağımlılıkta, genel yakalanır
            log.exception("Gemini isteği başarısız")
            raise LlmError(f"Gemini API hatası ({self._settings.gemini_model}): {exc}") from exc
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise LlmError("Gemini boş yanıt döndürdü")
        return text
