"""Kullanıcı sözlüğü: yanlış tanınan biçimleri doğru terimle değiştirme ve terimleri Whisper'a
ipucu (hotwords / başlangıç promptu) olarak verme."""

from __future__ import annotations

import re
from collections.abc import Sequence

from dikte.config import DictionaryEntry


def _variants(wrong: str) -> set[str]:
    """Türkçe İ/ı uyuşmazlıklarını da yakalamak için ek varyantlar üretir."""
    return {wrong, wrong.casefold(), wrong.replace("ı", "i").replace("İ", "I")}


# (tüm yanlış varyantların tek alternasyonu, grup sırasına göre terimler). Her varyant
# kendi yakalama grubundadır; eşleşen grubun numarası (`lastindex`) terimi verir.
CompiledRule = tuple[re.Pattern[str], tuple[str, ...]]


def compile_rules(entries: Sequence[DictionaryEntry]) -> list[CompiledRule]:
    """Sözlük girdilerinden tek bir birleşik regex derler. Bu derleme ölçülebilir şekilde
    yavaştır (büyük sözlüklerde her dikte için yüzlerce ms); sözlük değişmediği sürece
    yalnızca bir kez çağrılıp sonucu `apply_compiled` ile tekrar tekrar kullanılmalıdır."""
    variants: list[tuple[str, str]] = []
    for entry in entries:
        for wrong in entry.wrong:
            variants.extend((v, entry.term) for v in _variants(wrong) if v)
    if not variants:
        return []
    # Uzun varyant önce: alternasyon soldan ilk eşleşeni seçer, "gou land" "gou"dan önce denenmeli.
    variants.sort(key=lambda r: len(r[0]), reverse=True)
    alternation = "|".join(f"({re.escape(variant)})" for variant, _term in variants)
    pattern = re.compile(r"(?<!\w)(?:" + alternation + r")(?!\w)", re.IGNORECASE | re.UNICODE)
    return [(pattern, tuple(term for _variant, term in variants))]


def _term_already_present(text: str, pos: int, term: str) -> bool:
    candidate = text[pos : pos + len(term)]
    after = text[pos + len(term) : pos + len(term) + 1]
    return candidate.casefold() == term.casefold() and not (
        after and (after.isalnum() or after == "_")
    )


def apply_compiled(text: str, rules: list[CompiledRule]) -> str:
    """Tüm kuralları tek geçişte uygular: bir kuralın çıktısı başka bir kuralın girdisi
    olmaz ("React" → "React Native" zinciri oluşmaz) ve doğru terim zaten yazılıysa
    ("Visual Studio Code" içindeki "visual studio") dokunulmaz — işlem idempotenttir."""
    for pattern, terms in rules:
        parts: list[str] = []
        pos = 0
        match = pattern.search(text, pos)
        while match:
            term = terms[(match.lastindex or 1) - 1]
            if _term_already_present(text, match.start(), term):
                end = match.start() + len(term)
                parts.append(text[pos:end])
            else:
                # Terim düz metin olarak eklenir, regex değiştirme şablonu değildir: içinde
                # "\1" veya "\g<ad>" gibi bir dizi geçse de (ör. "C:\1") olduğu gibi yazılır.
                end = match.end()
                parts.append(text[pos : match.start()] + term)
            pos = end
            match = pattern.search(text, pos)
        parts.append(text[pos:])
        text = "".join(parts)
    return text


def apply_rules(text: str, entries: Sequence[DictionaryEntry]) -> str:
    """Tek seferlik kullanım: her çağrıda yeniden derler (sık çağrıda `apply_compiled`)."""
    return apply_compiled(text, compile_rules(entries))


def hotwords(entries: Sequence[DictionaryEntry]) -> str:
    """Whisper `hotwords` parametresi için terimlerin virgüllü listesi."""
    return ", ".join(e.term for e in entries)


def prompt_terms(entries: Sequence[DictionaryEntry], max_chars: int = 400) -> str:
    """Whisper başlangıç promptuna eklenen "Terimler: …" satırı; `max_chars`ta kesilir."""
    if not entries:
        return ""
    result = f"Terimler: {', '.join(e.term for e in entries)}"
    return result[:max_chars]
