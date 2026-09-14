from __future__ import annotations

import json
import logging
from collections.abc import Callable

from dikte.config import LlmSettings
from dikte.llm.keys import read_api_key
from dikte.llm.provider import LlmError

log = logging.getLogger(__name__)


def _default_client_factory(api_key: str | None, timeout: float, base_url: str | None = None):
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise LlmError('Anthropic SDK kurulu değil: uv pip install -e ".[anthropic]"') from exc
    kwargs = {"api_key": api_key, "timeout": timeout}
    if base_url:
        kwargs["base_url"] = base_url
    return Anthropic(**kwargs)


class AnthropicProvider:
    """Anthropic API'si ve Anthropic-uyumlu özel uç noktalar."""

    def __init__(
        self,
        settings: LlmSettings,
        client_factory: Callable | None = None,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        required_key: bool = True,
        name: str = "anthropic",
    ):
        self.name = name
        self._settings = settings
        self._model = model or settings.anthropic_model
        api_key = read_api_key(api_key_env, required=required_key)
        factory = client_factory or _default_client_factory
        self._client = (
            factory(api_key, settings.timeout_s, base_url)
            if base_url
            else factory(api_key, settings.timeout_s)
        )

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
                model=self._model,
                max_tokens=4096,
                temperature=temperature,
                system=sys_prompt,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            log.exception("Anthropic isteği başarısız")
            raise LlmError(f"Anthropic API hatası ({self._model}): {exc}") from exc
        text = "".join(getattr(b, "text", "") for b in msg.content)
        if json_schema is not None:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        return text
