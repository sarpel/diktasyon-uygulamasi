from __future__ import annotations

from typing import Protocol


class LlmError(Exception):
    pass


class LlmTruncatedError(LlmError):
    """Sağlayıcı çıktı sınırına ulaştı; yarım yanıt yapıştırılmamalı."""

    def __init__(self, provider: str):
        super().__init__(
            f"LLM yanıtı yarıda kesildi (çıktı sınırı, {provider}). Daha kısa bir metinle "
            "yeniden deneyin veya Ayarlar'dan daha büyük bağlam/çıktı sınırı olan bir model seçin."
        )


class LlmProvider(Protocol):
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
