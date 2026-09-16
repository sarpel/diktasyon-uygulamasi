from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from dikte.llm import prompts
from dikte.llm.diff import Change, word_changes
from dikte.llm.provider import LlmError, LlmProvider

log = logging.getLogger(__name__)

__all__ = ["Change", "CorrectionResult", "correct", "enhance_prompt", "translate"]


@dataclass(frozen=True)
class CorrectionResult:
    corrected_text: str
    changes: tuple[Change, ...]


def _parse_correction(reply: str, raw: str) -> CorrectionResult:
    try:
        data = json.loads(reply)
    except json.JSONDecodeError as exc:
        raise LlmError(f"LLM geçerli JSON döndürmedi: {reply[:120]!r}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("corrected_text"), str):
        raise LlmError("LLM yanıtında corrected_text yok")
    text = data["corrected_text"].strip()
    return CorrectionResult(corrected_text=text, changes=word_changes(raw, text))


def correct(provider: LlmProvider, raw: str, *, glossary: str = "") -> CorrectionResult:
    if not raw.strip():
        return CorrectionResult("", ())
    system = prompts.CORRECT_SYSTEM + (f"\n\n{glossary}" if glossary else "")
    reply = provider.complete(
        system,
        prompts.correct_user(raw),
        json_schema=prompts.CORRECT_SCHEMA,
        temperature=0.1,
    )
    return _parse_correction(reply, raw)


def translate(provider: LlmProvider, text: str) -> str:
    if not text.strip():
        return ""
    return provider.complete(
        prompts.TRANSLATE_SYSTEM, prompts.translate_user(text), temperature=0.2
    ).strip()


def enhance_prompt(provider: LlmProvider, text: str) -> str:
    if not text.strip():
        return ""
    return provider.complete(
        prompts.ENHANCE_SYSTEM, prompts.enhance_user(text), temperature=0.3
    ).strip()
