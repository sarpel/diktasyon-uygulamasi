from __future__ import annotations

import logging
from collections.abc import Callable

from dikte.config import LlmSettings
from dikte.llm.provider import LlmError

log = logging.getLogger(__name__)


def _default_client_factory(host: str, timeout: float):
    from ollama import Client

    return Client(host=host, timeout=timeout)


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: LlmSettings, client_factory: Callable | None = None):
        self._settings = settings
        self._client = (client_factory or _default_client_factory)(
            settings.ollama_host, settings.timeout_s
        )

    def warm_up(self) -> None:
        """Modeli boş bir istekle VRAM'e alır; ilk düzeltmedeki yükleme beklemesini kaldırır."""
        try:
            self._client.chat(
                model=self._settings.model,
                messages=[],
                keep_alive=self._settings.keep_alive,
            )
        except Exception as exc:  # noqa: BLE001 - ısındırma isteğe bağlıdır
            log.warning("Ollama ısındırma başarısız: %s", exc)
        else:
            log.info("Ollama modeli ısındırıldı: %s", self._settings.model)

    def unload(self) -> None:
        """Modeli VRAM'den düşürür (keep_alive=0); ölçüm/karşılaştırma senaryoları içindir."""
        try:
            self._client.chat(model=self._settings.model, messages=[], keep_alive=0)
        except Exception as exc:  # noqa: BLE001 - boşaltma başarısızlığı akışı durdurmaz
            log.warning("Ollama modeli boşaltılamadı (%s): %s", self._settings.model, exc)
        else:
            log.info("Ollama modeli boşaltıldı: %s", self._settings.model)

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict | None = None,
        temperature: float = 0.2,
    ) -> str:
        try:
            resp = self._client.chat(
                model=self._settings.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                format=json_schema,
                think=self._settings.think,
                options={
                    "temperature": temperature,
                    "top_p": self._settings.top_p,
                    "top_k": self._settings.top_k,
                    "num_ctx": self._settings.num_ctx,
                },
                keep_alive=self._settings.keep_alive,
            )
        except Exception as exc:
            log.exception("Ollama isteği başarısız")
            raise LlmError(
                f"Ollama'ya ulaşılamadı veya yanıt vermedi ({self._settings.ollama_host}): {exc}"
            ) from exc
        content = getattr(getattr(resp, "message", None), "content", None)
        if not isinstance(content, str) or not content.strip():
            raise LlmError("Ollama boş yanıt döndürdü")
        return content
