"""Yerel Ollama sunucusu için sağlayıcı (varsayılan); istek başına bağlam boyutu tahmini."""

from __future__ import annotations

import logging
from collections.abc import Callable

from dikte.config import LlmSettings
from dikte.llm.provider import LlmError, LlmTruncatedError

log = logging.getLogger(__name__)

# Türkçe metinde kaba tahmin: ~3 karakter/token. Çıktı (düzeltme/çeviri/prompt) girdinin
# yaklaşık iki katına kadar büyüyebilir; bağlam 2048'in katına yuvarlanır, VRAM için tavanlı.
_CHARS_PER_TOKEN = 3
_OUTPUT_FACTOR = 2
_CTX_STEP = 2048
_CTX_CAP = 32768


def estimate_num_ctx(system: str, user: str, *, base: int) -> int:
    """İstek için num_ctx: en az base; tahmini giriş+çıkış sığacak kadar büyür (tavan 32768).

    base tavandan büyükse kullanıcının açık ayarına dokunulmaz.
    """
    prompt_tokens = (len(system) + len(user)) / _CHARS_PER_TOKEN
    output_tokens = len(user) / _CHARS_PER_TOKEN * _OUTPUT_FACTOR
    needed = -(-int(prompt_tokens + output_tokens) // _CTX_STEP) * _CTX_STEP
    return max(base, min(needed, _CTX_CAP))


def _default_client_factory(host: str, timeout: float):
    from ollama import Client

    return Client(host=host, timeout=timeout)


class OllamaProvider:
    """Yerel Ollama sunucusu; `num_ctx` istek başına büyütülür, `think` ayardan gelir."""

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
                    "num_ctx": estimate_num_ctx(system, user, base=self._settings.num_ctx),
                },
                keep_alive=self._settings.keep_alive,
            )
        except Exception as exc:
            log.exception("Ollama isteği başarısız")
            raise LlmError(
                f"Ollama'ya ulaşılamadı veya yanıt vermedi ({self._settings.ollama_host}): {exc}"
            ) from exc
        if getattr(resp, "done_reason", None) == "length":
            log.warning("Ollama yanıtı bağlam/çıktı sınırında kesildi (%s)", self._settings.model)
            raise LlmTruncatedError(self.name)
        content = getattr(getattr(resp, "message", None), "content", None)
        if not isinstance(content, str) or not content.strip():
            raise LlmError("Ollama boş yanıt döndürdü")
        return content
