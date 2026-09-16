from __future__ import annotations

import re
from collections.abc import Sequence

from dikte.config import DictionaryEntry


def _variants(wrong: str) -> set[str]:
    """Türkçe İ/ı uyuşmazlıklarını da yakalamak için ek varyantlar üretir."""
    return {wrong, wrong.casefold(), wrong.replace("ı", "i").replace("İ", "I")}


def apply_rules(text: str, entries: Sequence[DictionaryEntry]) -> str:
    rules: list[tuple[str, re.Pattern[str], str]] = []
    for entry in entries:
        for wrong in entry.wrong:
            for variant in _variants(wrong):
                if not variant:
                    continue
                pattern = re.compile(
                    r"(?<!\w)" + re.escape(variant) + r"(?!\w)", re.IGNORECASE | re.UNICODE
                )
                rules.append((variant, pattern, entry.term))
    rules.sort(key=lambda r: len(r[0]), reverse=True)
    for _variant, pattern, term in rules:
        text = pattern.sub(term, text)
    return text


def hotwords(entries: Sequence[DictionaryEntry]) -> str:
    return ", ".join(e.term for e in entries)


def prompt_terms(entries: Sequence[DictionaryEntry], max_chars: int = 400) -> str:
    if not entries:
        return ""
    result = f"Terimler: {', '.join(e.term for e in entries)}"
    return result[:max_chars]
