from __future__ import annotations

import re
from collections.abc import Sequence

from dikte.config import DictionaryEntry


def _variants(wrong: str) -> set[str]:
    """Türkçe İ/ı uyuşmazlıklarını da yakalamak için ek varyantlar üretir."""
    return {wrong, wrong.casefold(), wrong.replace("ı", "i").replace("İ", "I")}


CompiledRule = tuple[re.Pattern[str], str]


def compile_rules(entries: Sequence[DictionaryEntry]) -> list[CompiledRule]:
    """Sözlük girdilerinden regex kurallarını derler. Bu derleme ölçülebilir şekilde
    yavaştır (büyük sözlüklerde her dikte için yüzlerce ms); sözlük değişmediği sürece
    yalnızca bir kez çağrılıp sonucu `apply_compiled` ile tekrar tekrar kullanılmalıdır."""
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
    return [(pattern, term) for _variant, pattern, term in rules]


def apply_compiled(text: str, rules: list[CompiledRule]) -> str:
    for pattern, term in rules:
        # `lambda _m: term` (düz metin), `pattern.sub(term, text)` yerine kullanılır: term
        # bir regex *değiştirme şablonu* değil düz metindir — içinde "\1" veya "\g<ad>" gibi
        # bir dizi geçerse (ör. kullanıcının eklediği "C:\1" gibi bir terim) ikincisi bunu
        # geri referans sanıp re.error fırlatır ya da yanlış metin üretir.
        text = pattern.sub(lambda _m, t=term: t, text)
    return text


def apply_rules(text: str, entries: Sequence[DictionaryEntry]) -> str:
    return apply_compiled(text, compile_rules(entries))


def hotwords(entries: Sequence[DictionaryEntry]) -> str:
    return ", ".join(e.term for e in entries)


def prompt_terms(entries: Sequence[DictionaryEntry], max_chars: int = 400) -> str:
    if not entries:
        return ""
    result = f"Terimler: {', '.join(e.term for e in entries)}"
    return result[:max_chars]
