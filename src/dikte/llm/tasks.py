"""LLM görevleri: dikte düzeltmesi (JSON + uzunluk denetimi), çeviri ve prompt iyileştirme."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

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
# özetlemiş, yanıtlamış ya da genişletmiş sayılır. Kısa metinlerde oran anlamsızdır.
_MIN_WORD_RATIO = 0.5
_MAX_WORD_RATIO = 1.6
_MIN_WORDS_FOR_CHECK = 4


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


def correction_looks_valid(raw: str, corrected: str) -> bool:
    """Düzeltmenin kelime sayısı ham metne göre makul aralıkta mı (0,5×–1,6×)?"""
    raw_words = len(raw.split())
    if raw_words < _MIN_WORDS_FOR_CHECK:
        return True
    ratio = len(corrected.split()) / raw_words
    return _MIN_WORD_RATIO <= ratio <= _MAX_WORD_RATIO


def correct(
    provider: LlmProvider, raw: str, *, glossary: str = "", sanity_check: bool = True
) -> CorrectionResult:
    """Ham transkripti LLM ile düzeltir (JSON şemalı yanıt); boş girdide LLM çağrılmaz.

    `glossary` sistem promptuna eklenir. Yanıt geçerli JSON değilse veya `sanity_check`
    açıkken kelime sayısı ham metne göre 0,5×–1,6× dışına çıkarsa `LlmError` fırlatır;
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
    if sanity_check and not correction_looks_valid(raw, result.corrected_text):
        raw_words, new_words = len(raw.split()), len(result.corrected_text.split())
        log.warning(
            "düzeltme ham metinden çok sapıyor (%d → %d kelime); ham metne dönülüyor",
            raw_words,
            new_words,
        )
        raise LlmError(
            f"düzeltme ham metinden çok farklı uzunlukta ({raw_words} → {new_words} kelime); "
            "model metni özetlemiş veya yanıtlamış olabilir. Sorun sürerse Ayarlar'dan başka "
            "bir model seçin."
        )
    return result


def translate(provider: LlmProvider, text: str) -> str:
    """Türkçe metni İngilizceye çevirir; boş girdide LLM çağrılmaz. Hatada `LlmError`."""
    if not text.strip():
        return ""
    return provider.complete(
        prompts.TRANSLATE_SYSTEM, prompts.translate_user(text), temperature=0.2
    ).strip()


def enhance_prompt(provider: LlmProvider, text: str) -> str:
    """Dikte edilen isteği İngilizce, bölümlü bir Markdown prompta dönüştürür. Hatada `LlmError`."""
    if not text.strip():
        return ""
    return provider.complete(
        prompts.ENHANCE_SYSTEM, prompts.enhance_user(text), temperature=0.3
    ).strip()
