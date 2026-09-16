"""Sesli komutlar: "yeni satır", "yeni paragraf", "son cümleyi sil".

Noktalama komutları ("noktalı virgül" vb.) bilinçli olarak desteklenmez — Türkçede bu
ifadeler gerçek kelime/deyim olarak da kullanılır, komut sanılıp yanlışlıkla değiştirilebilir.
"""

from __future__ import annotations

import re

_NEWLINE_RE = re.compile(r"\s*yeni sat[ıi]r\s*[,.]?\s*", re.IGNORECASE)
_PARAGRAPH_RE = re.compile(r"\s*yeni paragraf\s*[,.]?\s*", re.IGNORECASE)
_DELETE_LAST_SENTENCE_RE = re.compile(r"\s*son cümleyi sil\s*[,.]?\s*", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?]")


def _capitalize_turkish(text: str) -> str:
    """`str.capitalize()`in İngilizce `i`→`I` kuralını Türkçe `i`→`İ` ile değiştirir."""
    if not text:
        return text
    first = "İ" if text[0] == "i" else text[0].upper()
    return first + text[1:]


def _apply_break(text: str, pattern: re.Pattern[str], replacement: str) -> str:
    match = pattern.search(text)
    while match:
        text = text[: match.start()] + replacement + _capitalize_turkish(text[match.end() :])
        match = pattern.search(text)
    return text


def _delete_last_sentence(text: str) -> str:
    match = _DELETE_LAST_SENTENCE_RE.search(text)
    while match:
        before, after = text[: match.start()], text[match.end() :]
        boundary = 0
        for punct in _SENTENCE_END_RE.finditer(before):
            boundary = punct.end()
        kept = before[:boundary].rstrip()
        tail = _capitalize_turkish(after.lstrip())
        text = f"{kept} {tail}".strip() if kept and tail else (kept or tail)
        match = _DELETE_LAST_SENTENCE_RE.search(text)
    return text


def apply_commands(text: str) -> str:
    text = _delete_last_sentence(text)
    text = _apply_break(text, _NEWLINE_RE, "\n")
    text = _apply_break(text, _PARAGRAPH_RE, "\n\n")
    return text
