from __future__ import annotations

from collections.abc import Sequence

from dikte.core.state import Session


def to_markdown(sessions: Sequence[Session]) -> str:
    lines = ["# Dikte Geçmişi", ""]
    for s in sessions:
        lines.append(f"## {s.created_at:%d.%m.%Y %H:%M}")
        lines.append("")
        lines.append(s.corrected_text or s.raw_text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_text(sessions: Sequence[Session]) -> str:
    lines = [f"[{s.created_at:%d.%m.%Y %H:%M}] {s.corrected_text or s.raw_text}" for s in sessions]
    return ("\n".join(lines) + "\n") if lines else ""
