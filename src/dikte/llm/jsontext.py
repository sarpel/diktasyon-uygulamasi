"""LLM yanıtından JSON nesnesi çıkarımı.

Yerel sunucular response_format'ı yok sayıp yanıtı ```json çitine sarabilir ya da önüne
<think>…</think> düşünce bloğu ekleyebilir; tüm sağlayıcılar için tek ayıklayıcı.
"""

from __future__ import annotations

import json
import re

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CODE_FENCE = re.compile(r"^\s*```[\w-]*\s*$", re.MULTILINE)


def extract_json_object(text: str) -> str:
    """Düşünce bloklarını ve kod çitlerini atar, ilk ayrıştırılabilir en dış nesneyi döndürür.

    Nesne bulunamazsa temizlenmiş metin döner; ayrıştırma hatası çağırana kalır.
    """
    cleaned = _CODE_FENCE.sub("", _THINK.sub("", text)).strip()
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        try:
            obj, end = decoder.raw_decode(cleaned, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return cleaned[match.start() : end]
    return cleaned
