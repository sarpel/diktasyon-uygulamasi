"""LLM görevleri: dikte düzeltmesi (JSON + akıl sağlığı denetimi), çeviri ve prompt iyileştirme."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

from dikte.llm import prompts
from dikte.llm.diff import Change, word_changes
from dikte.llm.jsontext import extract_json_object
from dikte.llm.provider import LlmError, LlmProvider

log = logging.getLogger(__name__)

__all__ = [
    "Change",
    "CorrectionResult",
    "correct",
    "correction_looks_valid",
    "enhance_prompt",
    "translate",
]

# Düzeltme ham metnin kelime sayısından bu oranların dışına çıkarsa model metni
# özetlemiş, yanıtlamış ya da genişletmiş sayılır. Kısa metinlerde oran anlamsızdır;
# onlarda yalnızca mutlak bir tavan (ham kelime sayısı + _SHORT_MAX_EXTRA_WORDS) uygulanır.
# Alt sınır, düzeltmenin zaten atacağı dolgu kelimeleri ("ee", "şey"…) sayılmadan hesaplanır.
_MIN_WORD_RATIO = 0.5
_MAX_WORD_RATIO = 1.6
_MIN_WORDS_FOR_CHECK = 4
_SHORT_MAX_EXTRA_WORDS = 2

# İçerik örtüşmesi: ham metindeki içerik kelimelerinin (dolgu ve sayı sözcükleri hariç) en az
# bu kadarı düzeltmede (birebir, birleşmiş ya da yazımı düzeltilmiş hâliyle) bulunmalı. Gerçek
# düzeltmelerde oran genellikle %60'ın üstündedir; sohbet yanıtlarında %20'nin altına düşer.
_MIN_CONTENT_OVERLAP = 0.4
# Yazımı düzeltilmiş kelimeyi ("kubernetis" → "kubernetes", "jason" → "json") aynı saymak için
# difflib benzerlik eşiği.
_FUZZY_WORD_RATIO = 0.75

# Düzeltme isteminin silmesini istediği dolgular; örtüşme ve alt sınır hesabına girmez.
_FILLER_WORDS = frozenset(
    {"e", "ee", "eee", "ı", "ıı", "ııı", "ım", "hı", "hım", "hmm", "mm", "şey", "işte", "hani"}
)
# Rakama çevrilen sayı sözcükleri ("iki bin yirmi altı" → "2026") örtüşmeye girmez.
_NUMBER_WORDS = frozenset(
    {
        "sıfır",
        "bir",
        "iki",
        "üç",
        "dört",
        "beş",
        "altı",
        "yedi",
        "sekiz",
        "dokuz",
        "on",
        "yirmi",
        "otuz",
        "kırk",
        "elli",
        "altmış",
        "yetmiş",
        "seksen",
        "doksan",
        "yüz",
        "bin",
        "milyon",
        "milyar",
        "buçuk",
        "yüzde",
    }
)
_TOKEN_RE = re.compile(r"\w+")

# Çeviri ve prompt iyileştirme çıktısının karakter cinsinden üst sınırı: oran × girdi + pay.
# Sınırlar bilerek cömerttir; yalnızca modelin kontrolden çıktığı yanıtları yakalar.
_TRANSLATE_MAX_RATIO = 3
_TRANSLATE_SLACK_CHARS = 200
_ENHANCE_MAX_RATIO = 20
_ENHANCE_SLACK_CHARS = 4000


@dataclass(frozen=True)
class CorrectionResult:
    """Düzeltilmiş metin ve ham metne göre hesaplanan kelime düzeyi değişiklikler."""

    corrected_text: str
    changes: tuple[Change, ...]


def _parse_correction(reply: str, raw: str) -> CorrectionResult:
    try:
        data = json.loads(extract_json_object(reply))
    except json.JSONDecodeError as exc:
        # Yanıt metni mesaja girmez: dikte içeriği günlüğe ve arayüze sızmasın.
        raise LlmError(f"LLM geçerli JSON döndürmedi ({len(reply)} karakterlik yanıt)") from exc
    if not isinstance(data, dict) or not isinstance(data.get("corrected_text"), str):
        raise LlmError("LLM yanıtında corrected_text yok")
    text = data["corrected_text"].strip()
    return CorrectionResult(corrected_text=text, changes=word_changes(raw, text))


def _tokens(text: str) -> list[str]:
    """Türkçe büyük/küçük harf kurallarıyla (İ→i, I→ı) küçültülmüş, noktalamasız kelimeler."""
    folded = text.replace("İ", "i").replace("I", "ı").lower().replace("̇", "")
    return _TOKEN_RE.findall(folded)


def _non_filler_word_count(text: str) -> int:
    """Boşlukla ayrılmış kelimelerden dolgu olmayanların sayısı."""
    return sum(1 for word in text.split() if not set(_tokens(word)) <= _FILLER_WORDS)


def _fuzzy_match(word: str, candidates: Iterable[str]) -> bool:
    """`word`e yazımca yeterince benzeyen (difflib oranı ≥ eşik) bir aday var mı?"""
    for cand in candidates:
        matcher = SequenceMatcher(None, word, cand)
        if (
            matcher.real_quick_ratio() >= _FUZZY_WORD_RATIO
            and matcher.quick_ratio() >= _FUZZY_WORD_RATIO
            and matcher.ratio() >= _FUZZY_WORD_RATIO
        ):
            return True
    return False


def _content_overlap(raw: str, corrected: str) -> float:
    """Ham metindeki içerik kelimelerinden düzeltmede korunanların oranı (0–1).

    Bir kelime düzeltmede birebir, birleşik kelimenin parçası olarak ("kalk mam" → "kalkmam")
    ya da aynı harfle başlayan benzer yazımla ("kubernetis" → "kubernetes") geçiyorsa korunmuş
    sayılır. Benzerlik yalnızca aynı baş harfli adaylarla ölçülür: uzun metinlerde de hızlıdır."""
    content = set(_tokens(raw)) - _FILLER_WORDS - _NUMBER_WORDS
    if not content:
        return 1.0
    candidates = set(_tokens(corrected))
    joined = " ".join(candidates)  # Kelime boşluk içermez; alt dize araması sınır aşamaz.
    by_initial: dict[str, list[str]] = {}
    for cand in candidates:
        by_initial.setdefault(cand[0], []).append(cand)
    kept = sum(
        1
        for word in content
        if word in candidates
        or (len(word) >= 2 and word in joined)
        or _fuzzy_match(word, by_initial.get(word[0], ()))
    )
    return kept / len(content)


def _correction_problem(raw: str, corrected: str) -> str | None:
    """Düzeltme ham metinden çok sapıyorsa kullanıcıya gösterilecek neden; makulse None.

    Neden metni dikte içeriği taşımaz, yalnızca sayılar içerir."""
    if not corrected.strip():
        return None  # Boş düzeltme geçerlidir; denetleyici ham metne döner.
    raw_words, new_words = len(raw.split()), len(corrected.split())
    if raw_words < _MIN_WORDS_FOR_CHECK:
        too_far = new_words > raw_words + _SHORT_MAX_EXTRA_WORDS
    else:
        base = max(_non_filler_word_count(raw), 1)
        too_far = not base * _MIN_WORD_RATIO <= new_words <= raw_words * _MAX_WORD_RATIO
    if too_far:
        return f"çok farklı uzunlukta ({raw_words} → {new_words} kelime)"
    overlap = _content_overlap(raw, corrected)
    if overlap < _MIN_CONTENT_OVERLAP:
        return f"ham metnin kelimelerinin yalnızca %{round(overlap * 100)} kadarını içeriyor"
    return None


def correction_looks_valid(raw: str, corrected: str) -> bool:
    """Düzeltme ham metne göre makul mü?

    Dört kelime ve üstünde kelime sayısı 0,5×–1,6× aralığında olmalı (alt sınırda dolgular
    sayılmaz); daha kısa metinlerde en fazla iki kelime eklenebilir. Ayrıca ham metnin içerik
    kelimelerinin en az %40'ı düzeltmede korunmalı. Boş düzeltme geçerli sayılır."""
    return _correction_problem(raw, corrected) is None


def correct(
    provider: LlmProvider, raw: str, *, glossary: str = "", sanity_check: bool = True
) -> CorrectionResult:
    """Ham transkripti LLM ile düzeltir (JSON şemalı yanıt); boş girdide LLM çağrılmaz.

    `glossary` sistem promptuna eklenir. Yanıt geçerli JSON değilse veya `sanity_check`
    açıkken düzeltme `correction_looks_valid` denetiminden geçmezse `LlmError` fırlatır;
    denetleyici bu durumda ham metni sonuç olarak kullanır. `corrected_text` boş dönebilir."""
    if not raw.strip():
        return CorrectionResult("", ())
    system = prompts.CORRECT_SYSTEM + (f"\n\n{glossary}" if glossary else "")
    reply = provider.complete(
        system,
        prompts.correct_user(raw),
        json_schema=prompts.CORRECT_SCHEMA,
        temperature=0.1,
    )
    result = _parse_correction(reply, raw)
    problem = _correction_problem(raw, result.corrected_text) if sanity_check else None
    if problem is not None:
        log.warning("düzeltme ham metinden çok sapıyor (%s); ham metne dönülüyor", problem)
        raise LlmError(
            f"düzeltme ham metinden çok farklı: {problem}; model metni özetlemiş veya "
            "yanıtlamış olabilir. Sorun sürerse Ayarlar'dan başka bir model seçin."
        )
    return result


def _checked_output(reply: str, source: str, *, ratio: int, slack: int, label: str) -> str:
    """Çeviri/prompt çıktısını boşluğa ve kontrolsüz uzunluğa karşı denetler; hatada `LlmError`."""
    out = reply.strip()
    if not out:
        log.warning("%s: model boş yanıt döndürdü", label)
        raise LlmError(f"{label}: model boş yanıt döndürdü. Tekrar deneyin veya başka model seçin.")
    if len(out) > len(source) * ratio + slack:
        log.warning("%s: yanıt çok uzun (%d → %d karakter)", label, len(source), len(out))
        raise LlmError(
            f"{label}: yanıt girdiye göre çok uzun ({len(source)} → {len(out)} karakter); model "
            "metni işlemek yerine yanıtlamış olabilir. Sorun sürerse başka bir model seçin."
        )
    return out


def translate(provider: LlmProvider, text: str) -> str:
    """Türkçe metni İngilizceye çevirir; boş girdide LLM çağrılmaz.

    Yanıt boşsa veya girdinin 3 katı + 200 karakterden uzunsa `LlmError` fırlatır."""
    if not text.strip():
        return ""
    reply = provider.complete(
        prompts.TRANSLATE_SYSTEM, prompts.translate_user(text), temperature=0.2
    )
    return _checked_output(
        reply, text, ratio=_TRANSLATE_MAX_RATIO, slack=_TRANSLATE_SLACK_CHARS, label="Çeviri"
    )


def enhance_prompt(provider: LlmProvider, text: str) -> str:
    """Dikte edilen isteği İngilizce, bölümlü bir Markdown prompta dönüştürür.

    Promptlar doğal olarak genişler; yalnızca boş ya da girdinin 20 katı + 4000 karakterini
    aşan yanıtlar `LlmError` ile reddedilir."""
    if not text.strip():
        return ""
    reply = provider.complete(prompts.ENHANCE_SYSTEM, prompts.enhance_user(text), temperature=0.3)
    return _checked_output(
        reply,
        text,
        ratio=_ENHANCE_MAX_RATIO,
        slack=_ENHANCE_SLACK_CHARS,
        label="Prompt iyileştirme",
    )
