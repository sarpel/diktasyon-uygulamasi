from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from dikte.core.state import Session
from dikte.llm.tasks import Change

log = logging.getLogger(__name__)


class HistoryError(RuntimeError):
    """Geçmiş dosyası yazılamadı; çağıran katman kullanıcıya ne yapacağını söylemeli."""


def _to_json(s: Session) -> str:
    d = asdict(s)
    d["created_at"] = s.created_at.isoformat()
    return json.dumps(d, ensure_ascii=False)


def _from_json(line: str) -> Session | None:
    try:
        d = json.loads(line)
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        d["changes"] = tuple(Change(**c) for c in d.get("changes", ()))
        return Session(**d)
    except (ValueError, TypeError, KeyError) as exc:
        log.warning("geçmiş satırı atlandı: %s", exc)
        return None


class History:
    def __init__(self, path: Path, limit: int):
        self._path, self._limit = path, limit

    def load(self) -> tuple[Session, ...]:
        if self._limit <= 0 or not self._path.exists():
            return ()
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            log.exception("geçmiş okunamadı: %s", self._path)
            raise HistoryError(
                f"Geçmiş okunamadı ({self._path}): {exc}. Dosyaya okuma izniniz olduğunu "
                "kontrol edin."
            ) from exc
        sessions = [
            s for s in (_from_json(line) for line in lines if line.strip()) if s is not None
        ]
        return tuple(sessions[-self._limit :])

    def append(self, session: Session) -> None:
        if self._limit <= 0:
            return
        kept = self.load()[-(self._limit - 1) :] if self._limit > 1 else ()
        self._write((*kept, session))

    def update(self, session: Session) -> None:
        """Aynı `id`'ye sahip satır varsa yerinde değiştirir, yoksa `append` gibi ekler."""
        if self._limit <= 0:
            return
        existing = self.load()
        if any(s.id == session.id for s in existing):
            self._write(tuple(session if s.id == session.id else s for s in existing))
        else:
            self.append(session)

    def delete(self, session_id: str) -> None:
        self._write(tuple(s for s in self.load() if s.id != session_id))

    def clear(self) -> None:
        self._write(())

    def _write(self, sessions: tuple[Session, ...]) -> None:
        """Geçmişi tek seferde ve atomik olarak yazar (yarım dosya kalmaz)."""
        content = "".join(_to_json(s) + "\n" for s in sessions)
        tmp = self._path.with_suffix(".tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            if sys.platform != "win32":
                # Dikte edilen metnin kendisi burada; çok kullanıcılı bir Linux sisteminde
                # başkaları okumasın.
                tmp.chmod(0o600)
            tmp.replace(self._path)
        except OSError as exc:
            log.exception("geçmiş yazılamadı: %s", self._path)
            raise HistoryError(
                f"Geçmiş kaydedilemedi ({self._path}): {exc}. Diskte yer olduğunu ve "
                "klasöre yazma izniniz olduğunu kontrol edin."
            ) from exc
