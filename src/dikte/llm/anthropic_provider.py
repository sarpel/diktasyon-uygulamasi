from __future__ import annotations

import json
import logging
import os
from typing import Callable

from dikte.config import LlmSettings
from dikte.llm.provider import LlmError

log = logging.getLogger(__name__)


def _default_client_factory(api_key: str, timeout: float):
    from anthropic import Anthropic

    return Anthropic(api_key=api_key, timeout=timeout)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: LlmSettings, client_factory: Callable | None = None):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LlmError("ANTHROPIC_API_KEY ortam değişkeni tanımlı değil")
        self._settings = settings
        self._client = (client_factory or _default_client_factory)(api_key, settings.timeout_s)

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict | None = None,
        temperature: float = 0.2,
    ) -> str:
        sys_prompt = system
        if json_schema is not None:
            sys_prompt += (
                "\n\nRespond ONLY with a JSON object matching this schema:\n"
                + json.dumps(json_schema)
            )
        try:
            msg = self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=4096,
                temperature=temperature,
                system=sys_prompt,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            log.exception("Anthropic isteği başarısız")
            raise LlmError(f"Anthropic API hatası: {exc}") from exc
        text = "".join(getattr(b, "text", "") for b in msg.content)
        if json_schema is not None:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        return text
