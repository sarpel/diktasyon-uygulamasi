"""LLM sağlayıcı protokolü ve ortak hata tipleri."""

from __future__ import annotations

from typing import Protocol


class LlmError(Exception):
    """LLM çağrısı başarısız (ağ, SDK, anahtar, boş/geçersiz yanıt); mesaj arayüzde gösterilir."""


class LlmTruncatedError(LlmError):
    """Sağlayıcı çıktı sınırına ulaştı; yarım yanıt yapıştırılmamalı."""

    def __init__(self, provider: str):
        super().__init__(
            f"LLM yanıtı yarıda kesildi (çıktı sınırı, {provider}). Daha kısa bir metinle "
            "yeniden deneyin veya Ayarlar'dan daha büyük bağlam/çıktı sınırı olan bir model seçin."
        )


class LlmProvider(Protocol):
    """Tüm sağlayıcıların ortak arayüzü.

    `complete` engelleyicidir (worker iş parçacığından çağrılır) ve yalnızca `LlmError`
    (veya alt sınıfı) fırlatmalıdır. `json_schema` verilirse yanıt, o şemaya uyan tek bir
    JSON nesnesinin metnidir. İsteğe bağlı `warm_up()` yöntemi varsa denetleyici onu
    ön ısıtma için çağırır."""

    @property
    def name(self) -> str: ...

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict | None = None,
        temperature: float = 0.2,
    ) -> str: ...
