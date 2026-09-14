from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from dikte.core.state import Session
from dikte.llm.tasks import Change

log = logging.getLogger(__name__)


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
        lines = self._path.read_text(encoding="utf-8").splitlines()
        sessions = [
            s for s in (_from_json(line) for line in lines if line.strip()) if s is not None
        ]
        return tuple(sessions[-self._limit :])

    def append(self, session: Session) -> None:
        if self._limit <= 0:
            return
        kept = self.load()[-(self._limit - 1) :] if self._limit > 1 else ()
        content = "\n".join(_to_json(s) for s in (*kept, session)) + "\n"
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(self._path)
