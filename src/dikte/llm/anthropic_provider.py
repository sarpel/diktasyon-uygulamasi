from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from dikte.config import LlmSettings
from dikte.llm.keys import read_api_key
from dikte.llm.provider import LlmError

log = logging.getLogger(__name__)
# Anahtar istemeyen özel uç noktalar da bir değer bekler; SDK boş dizeyi (aksine ortam
# değişkenine düşmeden) açık bir kimlik bilgisi sayıp X-Api-Key başlığı doğrulamasında
# TypeError fırlatıyor. OpenAI sağlayıcısındaki yer tutucu deseniyle aynı çözüm.
PLACEHOLDER_KEY = "no-key"


def _default_client_factory(api_key: str | None, timeout: float, base_url: str | None = None):
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise LlmError('Anthropic SDK kurulu değil: uv pip install -e ".[anthropic]"') from exc
    key = api_key or PLACEHOLDER_KEY
    # SDK varsayılanı 2 yeniden deneme (zaman aşımları dahil): iptal edilen bir iş,
    # QThreadPool işçisini timeout_s × 3'e kadar işgal edebilir. İptal denetleyicide zaten
    # gen sayacıyla yapılıyor; SDK'nın kendi yeniden denemesine gerek yok.
    if base_url:
        return Anthropic(api_key=key, timeout=timeout, base_url=base_url, max_retries=0)
    return Anthropic(api_key=key, timeout=timeout, max_retries=0)


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
        # Anahtar yoksa boş değer verilir: SDK aksi hâlde ANTHROPIC_API_KEY /
        # ANTHROPIC_AUTH_TOKEN'a düşer ve kullanıcının gerçek anahtarını özel uç noktaya yollar.
        api_key = read_api_key(api_key_env, required=required_key) or ""
        factory = client_factory or _default_client_factory
        self._client: Any = (
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
                # 4096 uzun bir düzeltme/çeviri isteğinde yanıtı (JSON dahil) kesebilir —
                # kesilmiş JSON tümüyle kaybolur, kesilmiş düz metin sessizce kırpılır.
                max_tokens=8192,
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
