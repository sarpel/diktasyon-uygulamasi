"""API anahtarlarının ortam değişkenlerinden okunması.

Anahtarlar hiçbir zaman `config.json`'a yazılmaz ve loglanmaz; ayarlarda yalnızca
ortam değişkeninin **adı** saklanır, arayüz de sadece var/yok bilgisini gösterir.
"""

from __future__ import annotations

import os

from dikte.llm.provider import LlmError


def read_api_key(env_name: str, *, required: bool) -> str | None:
    """Ortam değişkeninden anahtarı okur. Zorunluysa ve yoksa LlmError verir."""
    value = os.environ.get(env_name, "").strip() if env_name else ""
    if value:
        return value
    if required:
        target = env_name or "API anahtarı ortam değişkeni"
        raise LlmError(
            f"{target} ortam değişkeni tanımlı değil. "
            "Anahtarı ortam değişkeni olarak tanımlayın; ayar dosyasına yazılmaz."
        )
    return None


def key_status(env_name: str) -> bool:
    """Arayüzde ✓/✗ göstermek için: anahtar tanımlı mı? Değeri asla döndürmez."""
    return bool(env_name) and bool(os.environ.get(env_name, "").strip())
