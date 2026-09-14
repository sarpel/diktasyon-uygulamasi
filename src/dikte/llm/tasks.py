from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from dikte.llm import prompts
from dikte.llm.provider import LlmError, LlmProvider

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Change:
    original: str
    replacement: str
    reason: str


@dataclass(frozen=True)
class CorrectionResult:
    corrected_text: str
    changes: tuple[Change, ...]


def _parse_correction(reply: str) -> CorrectionResult:
    try:
        data = json.loads(reply)
    except json.JSONDecodeError as exc:
        raise LlmError(f"LLM geçerli JSON döndürmedi: {reply[:120]!r}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("corrected_text"), str):
        raise LlmError("LLM yanıtında corrected_text yok")
    changes = tuple(
        Change(
            str(c.get("original", "")),
            str(c.get("replacement", "")),
            str(c.get("reason", "")),
        )
        for c in data.get("changes", [])
        if isinstance(c, dict)
    )
    return CorrectionResult(corrected_text=data["corrected_text"].strip(), changes=changes)


def correct(provider: LlmProvider, raw: str) -> CorrectionResult:
    if not raw.strip():
        return CorrectionResult("", ())
    reply = provider.complete(
        prompts.CORRECT_SYSTEM,
        prompts.correct_user(raw),
        json_schema=prompts.CORRECT_SCHEMA,
        temperature=0.1,
    )
    return _parse_correction(reply)


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
