from datetime import UTC, datetime

from dikte.core.history_export import to_markdown, to_text
from dikte.core.state import Session


def test_to_markdown_has_date_heading_and_text():
    s = Session(
        raw_text="ham",
        corrected_text="Düzeltilmiş.",
        created_at=datetime(2026, 1, 2, 9, 30, tzinfo=UTC),
    )
    md = to_markdown((s,))
    assert "## 02.01.2026 09:30" in md
    assert "Düzeltilmiş." in md


def test_to_markdown_falls_back_to_raw_text():
    s = Session(raw_text="yalnızca ham", created_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    assert "yalnızca ham" in to_markdown((s,))


def test_to_markdown_empty_sessions_has_title_only():
    md = to_markdown(())
    assert md.strip() == "# Dikte Geçmişi"


def test_to_text_produces_one_line_per_session():
    a = Session(corrected_text="A.", created_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC))
    b = Session(corrected_text="B.", created_at=datetime(2026, 1, 2, 9, 0, tzinfo=UTC))
    lines = to_text((a, b)).splitlines()
    assert len(lines) == 2
    assert lines[0] == "[01.01.2026 09:00] A."
    assert lines[1] == "[02.01.2026 09:00] B."


def test_to_text_empty_sessions_is_empty_string():
    assert to_text(()) == ""
