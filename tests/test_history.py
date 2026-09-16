from pathlib import Path

from dikte.core.history import History
from dikte.core.state import Session
from dikte.llm.tasks import Change


def test_append_and_load_roundtrip(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=10)
    s = Session(
        raw_text="a", corrected_text="A.", changes=(Change("a", "A.", "r"),), translation="x"
    )
    h.append(s)
    loaded = h.load()
    assert len(loaded) == 1 and loaded[0].id == s.id and loaded[0].changes[0].reason == "r"


def test_limit_trims_oldest(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=2)
    for i in range(4):
        h.append(Session(raw_text=str(i)))
    assert [s.raw_text for s in h.load()] == ["2", "3"]


def test_corrupt_lines_are_skipped(tmp_path: Path):
    p = tmp_path / "h.jsonl"
    p.write_text('{"bad json\n', encoding="utf-8")
    h = History(p, limit=5)
    h.append(Session(raw_text="ok"))
    assert [s.raw_text for s in h.load()] == ["ok"]


def test_zero_limit_disables_history(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=0)
    h.append(Session(raw_text="x"))
    assert h.load() == ()


def test_delete_removes_only_that_session(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=10)
    a, b = Session(raw_text="a"), Session(raw_text="b")
    h.append(a)
    h.append(b)
    h.delete(a.id)
    assert [s.id for s in h.load()] == [b.id]


def test_delete_unknown_id_is_noop(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=10)
    h.append(Session(raw_text="a"))
    h.delete("yok")
    assert len(h.load()) == 1


def test_clear_empties_file(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=10)
    h.append(Session(raw_text="a"))
    h.clear()
    assert h.load() == ()


def test_write_failure_raises_history_error(tmp_path: Path, monkeypatch):
    """Disk hatası sessizce yutulmaz; kullanıcıya iletilebilecek bir hata yükselir."""
    import pytest

    from dikte.core.history import HistoryError

    h = History(tmp_path / "h.jsonl", limit=5)

    def boom(*a, **k):
        raise OSError("disk dolu")

    monkeypatch.setattr(Path, "write_text", boom)
    with pytest.raises(HistoryError, match="Geçmiş kaydedilemedi"):
        h.append(Session(raw_text="x"))
