"""Geçmişin Markdown veya düz metin olarak dışa aktarılması."""

from __future__ import annotations

from collections.abc import Sequence

from dikte.core.state import Session


def _delivered(s: Session) -> str:
    """Kullanıcıya teslim edilen metin: çeviri/prompt modunda o çıktı, yoksa düzeltilmiş, o da
    yoksa ham metin."""
    return s.output_text or s.raw_text


def to_markdown(sessions: Sequence[Session]) -> str:
    """Oturum başına tarih başlığı ve teslim edilen metni içeren Markdown."""
    lines = ["# Dikte Geçmişi", ""]
    for s in sessions:
        lines.append(f"## {s.created_at:%d.%m.%Y %H:%M}")
        lines.append("")
        lines.append(_delivered(s))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_text(sessions: Sequence[Session]) -> str:
    """Oturum başına `[tarih] metin` satırı (teslim edilen metin); oturum yoksa boş dize."""
    lines = [f"[{s.created_at:%d.%m.%Y %H:%M}] {_delivered(s)}" for s in sessions]
    return ("\n".join(lines) + "\n") if lines else ""
