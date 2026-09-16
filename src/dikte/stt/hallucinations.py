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
# Kısmi eşleştirme (içerme/başlama) yalnız çok kelimeli, kendine özgü kalıplara uygulanır:
# "altyazı"/"çeviri" gibi tek kelimelik jenerik girdiler yalnız birebir eşleşmede eler
# ("Lütfen altyazı ekle", "Çeviriyi gönder" gerçek dikte olarak korunur).
_PARTIAL_PHRASES = tuple(p for p in KNOWN_PHRASES if len(p.split()) >= 2)


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
    if words <= MAX_CONTAINS_WORDS and any(p in normalized for p in _PARTIAL_PHRASES):
        return True
    return words <= MAX_PREFIX_WORDS and normalized.startswith(_PARTIAL_PHRASES)


def filter_segments(
    segments: tuple[Segment, ...],
    *,
    no_speech_threshold: float,
    log_prob_threshold: float | None = None,
) -> tuple[Segment, ...]:
    """Uydurma kalıpları ve konuşma olmadığı belli segmentleri eler; yeni bir demet döner."""
    # faster-whisper semantiği: sessizlik kararı yüksek no_speech_prob VE düşük
    # avg_logprob birlikte sağlanınca verilir; tek başına no_speech_prob yetmez.
    kept: list[Segment] = []
    for s in segments:
        silent = s.no_speech_prob >= no_speech_threshold
        if silent and log_prob_threshold is not None:
            silent = s.avg_logprob < log_prob_threshold
        if not silent and not is_hallucination(s.text):
            kept.append(s)
    return tuple(kept)
