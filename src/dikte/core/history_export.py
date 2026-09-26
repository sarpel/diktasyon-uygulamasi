"""Geçmişin Markdown veya düz metin olarak dışa aktarılması."""

from __future__ import annotations

from collections.abc import Sequence

from dikte.core.state import Session


def to_markdown(sessions: Sequence[Session]) -> str:
    """Oturum başına tarih başlığı ve düzeltilmiş (yoksa ham) metin içeren Markdown."""
    lines = ["# Dikte Geçmişi", ""]
    for s in sessions:
        lines.append(f"## {s.created_at:%d.%m.%Y %H:%M}")
        lines.append("")
        lines.append(s.corrected_text or s.raw_text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_text(sessions: Sequence[Session]) -> str:
    """Oturum başına `[tarih] metin` satırı; oturum yoksa boş dize."""
    lines = [f"[{s.created_at:%d.%m.%Y %H:%M}] {s.corrected_text or s.raw_text}" for s in sessions]
    return ("\n".join(lines) + "\n") if lines else ""
