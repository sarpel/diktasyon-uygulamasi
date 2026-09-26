"""Ham ve düzeltilmiş metin arasındaki kelime düzeyi farklar.

LLM'den değişiklik listesi istemek çıktı token'ını artırıyor ve liste güvenilir olmuyordu;
fark burada deterministik olarak hesaplanır.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

_WORD = re.compile(r"\S+")
_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)


@dataclass(frozen=True)
class Change:
    """Tek bir kelime düzeyi değişiklik; `start`/`end` düzeltilmiş metindeki aralıktır."""

    original: str
    replacement: str
    reason: str
    start: int = -1  # düzeltilmiş metindeki karakter aralığı; eski kayıtlarda -1
    end: int = -1


def _norm(word: str) -> str:
    return unicodedata.normalize("NFKC", _PUNCT.sub("", word)).casefold()


def _reason(a: list[str], b: list[str]) -> str:
    if not a:
        return "eklendi"
    if not b:
        return "silindi"
    if [_norm(w) for w in a] == [_norm(w) for w in b]:
        return "noktalama/büyük harf"
    return "değiştirildi"


def word_changes(original: str, corrected: str) -> tuple[Change, ...]:
    """İki metin arasındaki kelime farkları; `reason` eklendi/silindi/değiştirildi ya da
    "noktalama/büyük harf" olur. Silmede aralık boştur (önceki kelimenin sonu)."""
    a_spans = [m.span() for m in _WORD.finditer(original)]
    b_spans = [m.span() for m in _WORD.finditer(corrected)]
    a = [original[s:e] for s, e in a_spans]
    b = [corrected[s:e] for s, e in b_spans]
    # Eşleştirme normalize edilmiş kelimeler üzerinden yapılır; böylece cümledeki
    # başka bir yerdeki büyük/küçük harf ya da noktalama farkı, asıl değişen
    # kelimenin hizalanmasını bozmaz.
    a_norm = [_norm(w) for w in a]
    b_norm = [_norm(w) for w in b]
    out: list[Change] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a_norm, b_norm, autojunk=False).get_opcodes():
        if tag == "equal":
            # Normalize edilmiş hâliyle aynı olan ardışık kelimeler tek blok olarak
            # gelir; yalnızca ham metni gerçekten farklı olan kelimeler bildirilir,
            # aradaki değişmemiş kelimeler blokla birleştirilmez.
            for k in range(i2 - i1):
                aw, bw = a[i1 + k], b[j1 + k]
                if aw == bw:
                    continue
                start, end = b_spans[j1 + k]
                out.append(Change(aw, bw, "noktalama/büyük harf", start, end))
            continue
        a_words, b_words = a[i1:i2], b[j1:j2]
        if j1 < j2:
            start, end = b_spans[j1][0], b_spans[j2 - 1][1]
        else:  # silme: önceki kelimenin sonu (yoksa 0)
            start = end = b_spans[j1 - 1][1] if j1 > 0 else 0
        out.append(
            Change(" ".join(a_words), " ".join(b_words), _reason(a_words, b_words), start, end)
        )
    return tuple(out)
