"""OpenAI ve OpenAI-uyumlu (LM Studio, vLLM, OpenRouter…) uç noktalar için sağlayıcı."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from dikte.config import LlmSettings
from dikte.llm.jsontext import extract_json_object
from dikte.llm.keys import read_api_key
from dikte.llm.provider import LlmError, LlmTruncatedError

log = logging.getLogger(__name__)
SCHEMA_NAME = "dikte"
# Anahtar istemeyen yerel sunucular da bir değer bekler; SDK boş anahtarı reddeder.
PLACEHOLDER_KEY = "sk-no-key"


def _default_client_factory(*, base_url: str, api_key: str | None, timeout: float):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LlmError('OpenAI SDK kurulu değil: uv pip install -e ".[openai]"') from exc
    # max_retries=0: SDK varsayılanı 2 yeniden deneme (zaman aşımları dahil), iptal edilen
    # bir iş worker'ı timeout_s × 3'e kadar işgal edebilir; iptal zaten gen sayacıyla yapılıyor.
    return OpenAI(
        base_url=base_url, api_key=api_key or PLACEHOLDER_KEY, timeout=timeout, max_retries=0
    )


# SDK kurulu olsun olmasın yakalanan sınıflar: yerel sunucular json_schema'yı 400 yerine
# istemci tarafı doğrulamasıyla da reddedebilir.
_BUILTIN_SCHEMA_ERRORS: tuple[type[BaseException], ...] = (ValueError, TypeError)


def _schema_unsupported_errors() -> tuple[type[BaseException], ...]:
    """json_schema'yı reddeden sunucuların hata sınıfları; SDK yoksa yalnızca yerleşikler."""
    try:
        from openai import BadRequestError
    except ImportError:
        return _BUILTIN_SCHEMA_ERRORS
    return (BadRequestError, *_BUILTIN_SCHEMA_ERRORS)


class OpenAiCompatProvider:
    def __init__(
        self,
        settings: LlmSettings,
        *,
        base_url: str,
        model: str,
        api_key_env: str,
        required_key: bool,
        name: str = "openai",
        client_factory: Callable | None = None,
    ):
        self.name = name
        self._settings, self._model = settings, model
        api_key = read_api_key(api_key_env, required=required_key)
        self._client = (client_factory or _default_client_factory)(
            base_url=base_url, api_key=api_key, timeout=settings.timeout_s
        )

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict | None = None,
        temperature: float = 0.2,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            if json_schema is None:
                return self._text(self._create(messages, temperature, None))
            return extract_json_object(self._complete_json(messages, temperature, json_schema))
        except LlmError:
            raise
        except Exception as exc:  # SDK hata sınıfları isteğe bağlı bağımlılıkta, genel yakalanır
            log.exception("OpenAI-uyumlu istek başarısız")
            raise LlmError(f"OpenAI-uyumlu API hatası ({self._model}): {exc}") from exc

    # ---- iç
    def _complete_json(self, messages: list[dict], temperature: float, schema: dict) -> str:
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": SCHEMA_NAME, "schema": schema, "strict": False},
        }
        try:
            return self._text(self._create(messages, temperature, response_format))
        except _schema_unsupported_errors() as exc:
            log.info("sunucu json_schema desteklemiyor (%s); json_object ile deneniyor", exc)
        fallback = [dict(m) for m in messages]
        fallback[0]["content"] += (
            "\n\nRespond ONLY with a JSON object matching this schema:\n" + json.dumps(schema)
        )
        return self._text(self._create(fallback, temperature, {"type": "json_object"}))

    def _create(self, messages: list[dict], temperature: float, response_format: dict | None):
        kwargs = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "top_p": self._settings.top_p,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        return self._client.chat.completions.create(**kwargs)

    def _text(self, response) -> str:
        choices = getattr(response, "choices", None) or []
        if choices and getattr(choices[0], "finish_reason", None) == "length":
            log.warning("OpenAI-uyumlu yanıt çıktı sınırında kesildi (%s)", self._model)
            raise LlmTruncatedError(self.name)
        content = (
            getattr(getattr(choices[0], "message", None), "content", None) if choices else None
        )
        if not isinstance(content, str) or not content.strip():
            raise LlmError("OpenAI-uyumlu sağlayıcı boş yanıt döndürdü")
        return content
