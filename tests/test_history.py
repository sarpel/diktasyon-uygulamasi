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


def test_update_replaces_existing_session_without_growing_count(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=10)
    s = Session(raw_text="a", corrected_text="A.")
    h.append(s)
    edited = s.with_(corrected_text="A edited.")
    h.update(edited)
    loaded = h.load()
    assert len(loaded) == 1
    assert loaded[0].id == s.id and loaded[0].corrected_text == "A edited."


def test_update_appends_when_id_unknown(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=10)
    h.append(Session(raw_text="a"))
    new = Session(raw_text="b")
    h.update(new)
    assert [s.raw_text for s in h.load()] == ["a", "b"]


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


# ---- sürüm geri alma / bilinmeyen alanlar


def test_unknown_keys_are_ignored_not_line_dropped(tmp_path: Path):
    """Yeni sürümün eklediği alanlar eski sürümde satırı atlatmamalı (geçmiş kaybı)."""
    import json

    p = tmp_path / "h.jsonl"
    s = Session(raw_text="gelecek", changes=(Change("a", "b", "r"),))
    from dikte.core.history import _to_json

    d = json.loads(_to_json(s))
    d["future_field"] = 42
    d["changes"][0]["confidence"] = 0.9
    p.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")
    loaded = History(p, limit=5).load()
    assert [x.raw_text for x in loaded] == ["gelecek"]
    assert loaded[0].changes[0].replacement == "b"


def test_missing_optional_keys_get_defaults(tmp_path: Path):
    p = tmp_path / "h.jsonl"
    p.write_text(
        '{"id": "abc", "created_at": "2026-01-01T10:00:00", "raw_text": "eski"}\n',
        encoding="utf-8",
    )
    loaded = History(p, limit=5).load()
    assert loaded[0].id == "abc" and loaded[0].profile == "" and loaded[0].changes == ()


def test_unparseable_lines_are_backed_up_before_rewrite(tmp_path: Path):
    p = tmp_path / "h.jsonl"
    p.write_text('{"bad json\n', encoding="utf-8")
    h = History(p, limit=5)
    h.append(Session(raw_text="ok"))
    bak = tmp_path / "h.jsonl.bak"
    assert bak.exists() and '{"bad json' in bak.read_text(encoding="utf-8")
    assert [s.raw_text for s in h.load()] == ["ok"]


# ---- saklama süresi


def _dated(days_ago: float, text: str, now):
    from datetime import timedelta

    return Session(raw_text=text, created_at=now - timedelta(days=days_ago))


def test_retention_days_hides_and_drops_old_sessions(tmp_path: Path):
    from datetime import datetime

    now = datetime(2026, 9, 25, 12, 0)
    p = tmp_path / "h.jsonl"
    writer = History(p, limit=10)
    writer.append(_dated(40, "eski", now))
    writer.append(_dated(1, "yeni", now))
    h = History(p, limit=10, retention_days=30, clock=lambda: now)
    assert [s.raw_text for s in h.load()] == ["yeni"]
    h.append(_dated(0, "bugün", now))
    assert "eski" not in p.read_text(encoding="utf-8")


def test_retention_zero_keeps_everything(tmp_path: Path):
    from datetime import datetime

    now = datetime(2026, 9, 25, 12, 0)
    h = History(tmp_path / "h.jsonl", limit=10, retention_days=0, clock=lambda: now)
    h.append(_dated(4000, "çok eski", now))
    assert [s.raw_text for s in h.load()] == ["çok eski"]


# ---- prune


def test_prune_with_zero_limit_deletes_file(tmp_path: Path):
    p = tmp_path / "h.jsonl"
    History(p, limit=10).append(Session(raw_text="gizli"))
    (tmp_path / "h.jsonl.bak").write_text("x\n", encoding="utf-8")
    History(p, limit=0).prune()
    assert not p.exists()
    assert not (tmp_path / "h.jsonl.bak").exists()


def test_prune_enforces_limit_and_retention(tmp_path: Path):
    from datetime import datetime

    now = datetime(2026, 9, 25, 12, 0)
    p = tmp_path / "h.jsonl"
    w = History(p, limit=10)
    w.append(_dated(100, "eski", now))
    for i in range(3):
        w.append(_dated(0, f"s{i}", now))
    removed = History(p, limit=2, retention_days=30, clock=lambda: now).prune()
    assert removed == 2
    content = p.read_text(encoding="utf-8")
    assert "eski" not in content and "s0" not in content
    assert [s.raw_text for s in History(p, limit=10).load()] == ["s1", "s2"]


def test_prune_missing_file_is_noop(tmp_path: Path):
    assert History(tmp_path / "yok.jsonl", limit=5).prune() == 0


def test_clear_also_removes_backup(tmp_path: Path):
    p = tmp_path / "h.jsonl"
    h = History(p, limit=5)
    h.append(Session(raw_text="a"))
    (tmp_path / "h.jsonl.bak").write_text("x\n", encoding="utf-8")
    h.clear()
    assert not (tmp_path / "h.jsonl.bak").exists()


# ---- önbellek


def test_load_uses_cache_until_file_changes(tmp_path: Path, monkeypatch):
    from dikte.core import history as history_mod

    p = tmp_path / "h.jsonl"
    h = History(p, limit=10)
    h.append(Session(raw_text="a"))
    h.load()
    parsed = []
    real = history_mod._from_json
    monkeypatch.setattr(history_mod, "_from_json", lambda line: parsed.append(1) or real(line))
    h.load()
    h.append(Session(raw_text="b"))  # kendi yazdığı dosyayı tekrar ayrıştırmaz
    assert h.load()[-1].raw_text == "b"
    assert parsed == []
    # Dışarıdan değişiklik (başka örnek/el ile düzenleme) algılanır.
    other = History(p, limit=10)
    other.append(Session(raw_text="dış değişiklik uzun metin"))
    assert h.load()[-1].raw_text == "dış değişiklik uzun metin"
    assert parsed


# ---- yinelenen kimlik / boş oturum


def test_append_with_existing_id_replaces_instead_of_duplicating(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=10)
    s = Session(raw_text="a", corrected_text="A.")
    h.append(Session(raw_text="önce"))
    h.append(s)
    h.append(Session(raw_text="sonra"))
    h.append(s.with_(corrected_text="A düzeltildi."))
    loaded = h.load()
    assert [x.raw_text for x in loaded] == ["önce", "a", "sonra"]
    assert loaded[1].corrected_text == "A düzeltildi."


def test_empty_session_is_not_persisted(tmp_path: Path):
    p = tmp_path / "h.jsonl"
    h = History(p, limit=10)
    h.append(Session())
    h.update(Session())
    assert h.load() == () and not p.exists()


def test_update_with_empty_text_keeps_existing_row(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=10)
    s = Session(raw_text="a", corrected_text="A.")
    h.append(s)
    h.update(Session(id=s.id))
    assert [x.corrected_text for x in h.load()] == ["A."]
