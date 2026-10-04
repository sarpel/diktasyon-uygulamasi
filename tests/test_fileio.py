import os
import sys
from pathlib import Path

import numpy as np
import pytest

from dikte.config import Settings, save_settings
from dikte.core.fileio import write_private_atomic
from dikte.core.history import History
from dikte.core.state import Session

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX izinleri")


@pytest.fixture
def open_umask():
    """umask 0: geçici dosya sonradan chmod ile değil, oluşturulurken 0600 olmalı."""
    old = os.umask(0)
    try:
        yield
    finally:
        os.umask(old)


@pytest.fixture
def fsync_probe(monkeypatch):
    """Her fsync çağrısında dosyanın o anki iznini kaydeder; replace sırası da izlenir."""
    events: list[tuple[str, int]] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        events.append(("fsync", os.fstat(fd).st_mode & 0o777))
        real_fsync(fd)

    def replace(src, dst):
        events.append(("replace", 0))
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    return events


def _assert_private_and_synced(path: Path, events) -> None:
    assert ("fsync" in [e[0] for e in events]) and events[-1][0] == "replace"
    assert events.index(next(e for e in events if e[0] == "fsync")) < len(events) - 1
    if sys.platform != "win32":
        assert all(mode == 0o600 for kind, mode in events if kind == "fsync")
        assert path.stat().st_mode & 0o777 == 0o600
    assert not [p for p in path.parent.iterdir() if p.name.endswith(".tmp")]


@posix_only
def test_write_private_atomic_creates_0600_and_fsyncs(tmp_path, open_umask, fsync_probe):
    p = tmp_path / "a.json"
    write_private_atomic(p, b"veri")
    assert p.read_bytes() == b"veri"
    _assert_private_and_synced(p, fsync_probe)


def test_write_private_atomic_overwrites_and_survives_stale_tmp(tmp_path):
    p = tmp_path / "a.json"
    (tmp_path / "a.tmp").write_text("eski çökme artığı", encoding="utf-8")
    write_private_atomic(p, b"1")
    write_private_atomic(p, b"2")
    assert p.read_bytes() == b"2"


def test_write_private_atomic_cleans_tmp_on_failure(tmp_path, monkeypatch):
    def boom(fd):
        raise OSError("disk dolu")

    monkeypatch.setattr(os, "fsync", boom)
    p = tmp_path / "a.json"
    with pytest.raises(OSError, match="disk dolu"):
        write_private_atomic(p, b"x")
    assert list(tmp_path.iterdir()) == []


@posix_only
def test_history_write_is_private_and_synced(tmp_path, open_umask, fsync_probe):
    p = tmp_path / "history.jsonl"
    History(p, limit=5).append(Session(raw_text="gizli"))
    _assert_private_and_synced(p, fsync_probe)


@posix_only
def test_settings_write_is_private_and_synced(tmp_path, open_umask, fsync_probe):
    p = tmp_path / "config.json"
    save_settings(Settings(), p)
    _assert_private_and_synced(p, fsync_probe)


@posix_only
def test_failed_audio_write_is_private_and_synced(tmp_path, open_umask, fsync_probe):
    from dikte.audio.wav import load_wav, save_wav

    p = tmp_path / "failed" / "last.wav"
    save_wav(p, np.zeros(1600, dtype=np.float32))
    assert load_wav(p).shape == (1600,)
    _assert_private_and_synced(p, fsync_probe)
