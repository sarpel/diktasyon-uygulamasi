"""Whisper'ın sessizlik/gürültü üzerinde ürettiği bilinen uydurma metinlerin elenmesi.

Model, eğitim verisindeki altyazı dosyalarından öğrendiği kalıpları sessiz parçalarda
tekrar eder ("Altyazı M.K.", "İzlediğiniz için teşekkürler"). Bu kalıplar yalnızca tek
başına bir segmenti kapladığında elenir; gerçek bir cümlenin içinde geçtiğinde korunur.
"""

from __future__ import annotations

import re
import unicodedata

from dikte.stt.result import Segment

KNOWN_PHRASES: tuple[str, ...] = (
    "altyazi m k",
    "altyazi mk",
    "altyazi",
    "altyazi cevirmeni",
    "izlediginiz icin tesekkurler",
    "izlediginiz icin tesekkur ederim",
    "abone olmayi unutmayin",
    "beni izlemeye devam edin",
    "bu videoyu begendiyseniz",
    "kanalima abone olun",
    "ceviri",
    "subtitles by",
    "amara org community",
    "thanks for watching",
)
# Kalıp içerme kontrolü yalnızca çok kısa segmentlerde yapılır; uzun cümleler gerçek konuşmadır
# ("Bugün toplantıda altyazı ekleme özelliğini konuştuk" elenmemeli).
MAX_CONTAINS_WORDS = 4
# Kalıpla *başlayan* kısa segmentler de uydurmadır ("Subtitles by the Amara.org community").
MAX_PREFIX_WORDS = 8
_DOTLESS_I = str.maketrans({"ı": "i"})
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold().translate(_DOTLESS_I))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(_NON_WORD.sub(" ", stripped).split())


def is_hallucination(text: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    if normalized in KNOWN_PHRASES:
        return True
    words = len(normalized.split())
    if words <= MAX_CONTAINS_WORDS and any(p in normalized for p in KNOWN_PHRASES):
        return True
    return words <= MAX_PREFIX_WORDS and normalized.startswith(KNOWN_PHRASES)


def filter_segments(
    segments: tuple[Segment, ...], *, no_speech_threshold: float
) -> tuple[Segment, ...]:
    """Uydurma kalıpları ve konuşma olmadığı belli segmentleri eler; yeni bir demet döner."""
    return tuple(
        s
        for s in segments
        if s.no_speech_prob < no_speech_threshold and not is_hallucination(s.text)
    )
