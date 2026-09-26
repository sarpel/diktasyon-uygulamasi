"""Dikte geçmişinin JSONL dosyasında saklanması (sınır, saklama süresi, bozuk satır yedeği)."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta
from pathlib import Path

from dikte.core.state import Session
from dikte.llm.tasks import Change

log = logging.getLogger(__name__)

_SESSION_FIELDS = frozenset(f.name for f in fields(Session))
_CHANGE_FIELDS = frozenset(f.name for f in fields(Change))


class HistoryError(RuntimeError):
    """Geçmiş dosyası yazılamadı; çağıran katman kullanıcıya ne yapacağını söylemeli."""


def _to_json(s: Session) -> str:
    d = asdict(s)
    d["created_at"] = s.created_at.isoformat()
    return json.dumps(d, ensure_ascii=False)


def _from_json(line: str) -> Session | None:
    """Bilinmeyen alanlar (daha yeni bir sürümün yazdıkları) yok sayılır, eksik isteğe bağlı
    alanlar varsayılanını alır: sürüm geri alındığında geçmiş satırları kaybolmamalı."""
    try:
        d = json.loads(line)
        if not isinstance(d, dict):
            raise TypeError("satır bir JSON nesnesi değil")
        d = {k: v for k, v in d.items() if k in _SESSION_FIELDS}
        if "created_at" in d:
            d["created_at"] = datetime.fromisoformat(d["created_at"])
        d["changes"] = tuple(
            Change(**{k: v for k, v in c.items() if k in _CHANGE_FIELDS})
            for c in d.get("changes", ())
        )
        return Session(**d)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        log.warning("geçmiş satırı okunamadı: %s", exc)
        return None


def _naive(dt: datetime) -> datetime:
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo is not None else dt


@dataclass(frozen=True)
class _Parsed:
    stamp: tuple[int, int]  # (mtime_ns, size): dosya değişince önbellek geçersiz
    sessions: tuple[Session, ...]
    bad_lines: tuple[str, ...]  # ayrıştırılamayan satırlar; yeniden yazmadan önce yedeklenir


class History:
    """`history.jsonl` üzerinde dikte geçmişi: en fazla `limit` oturum, eskiden yeniye.

    `retention_days > 0` ise daha eski oturumlar okunurken gizlenir, bir sonraki yazımda
    (veya `prune`) diskten de düşer. `limit <= 0` geçmişi kapatır. Okuma/yazma/silme
    hataları kullanıcıya gösterilecek mesajla `HistoryError` olarak fırlatılır. Dosya
    değişmedikçe ayrıştırma sonucu önbellekten okunur (mtime + boyut)."""

    def __init__(
        self,
        path: Path,
        limit: int,
        *,
        retention_days: int = 0,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self._path, self._limit = path, limit
        self._retention_days = retention_days
        self._clock = clock
        self._cache: _Parsed | None = None

    @property
    def backup_path(self) -> Path:
        return self._path.with_name(self._path.name + ".bak")

    def load(self) -> tuple[Session, ...]:
        """Sınır ve saklama süresi uygulanmış oturumlar; bozuk satırlar atlanır."""
        if self._limit <= 0:
            return ()
        return self._visible(self._read().sessions)

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
        self._remove(self.backup_path)

    def prune(self) -> int:
        """Sınırı ve saklama süresini diske uygular; kaldırılan oturum sayısını döndürür.
        `limit=0` ise geçmiş dosyası (ve yedeği) tamamen silinir — dikte edilmiş metin,
        kullanıcı geçmişi kapattıktan sonra diskte kalmamalı. Bozuk satır varsa dosya
        yeniden yazılır (satırlar `.bak`'a taşınır). Açılışta ve ayar değişince çağrılır."""
        if self._limit <= 0:
            removed = len(self._read().sessions) if self._path.exists() else 0
            self._remove(self._path)
            self._remove(self.backup_path)
            self._cache = None
            return removed
        if not self._path.exists():
            return 0
        parsed = self._read()
        kept = self._visible(parsed.sessions)
        removed = len(parsed.sessions) - len(kept)
        if removed or parsed.bad_lines:
            self._write(kept)
        return removed

    # ---- iç yardımcılar
    def _visible(self, sessions: tuple[Session, ...]) -> tuple[Session, ...]:
        if self._retention_days > 0:
            cutoff = self._clock() - timedelta(days=self._retention_days)
            sessions = tuple(s for s in sessions if _naive(s.created_at) >= cutoff)
        return sessions[-self._limit :] if self._limit > 0 else ()

    def _stamp(self) -> tuple[int, int] | None:
        try:
            st = self._path.stat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            log.exception("geçmiş okunamadı: %s", self._path)
            raise HistoryError(
                f"Geçmiş okunamadı ({self._path}): {exc}. Dosyaya okuma izniniz olduğunu "
                "kontrol edin."
            ) from exc
        return (st.st_mtime_ns, st.st_size)

    def _read(self) -> _Parsed:
        """Dosyayı ayrıştırır; dosya son okumadan beri değişmediyse önbelleği döndürür."""
        stamp = self._stamp()
        if stamp is None:
            self._cache = None
            return _Parsed((0, 0), (), ())
        if self._cache is not None and self._cache.stamp == stamp:
            return self._cache
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            log.exception("geçmiş okunamadı: %s", self._path)
            raise HistoryError(
                f"Geçmiş okunamadı ({self._path}): {exc}. Dosyaya okuma izniniz olduğunu "
                "kontrol edin."
            ) from exc
        sessions: list[Session] = []
        bad: list[str] = []
        for line in lines:
            if not line.strip():
                continue
            s = _from_json(line)
            if s is None:
                bad.append(line)
            else:
                sessions.append(s)
        self._cache = _Parsed(stamp, tuple(sessions), tuple(bad))
        return self._cache

    def _backup_bad_lines(self) -> None:
        """Ayrıştırılamayan satırlar yeniden yazımda kaybolmasın: `.bak` dosyasına eklenir."""
        bad = self._read().bad_lines if self._path.exists() else ()
        if not bad:
            return
        bak = self.backup_path
        try:
            with bak.open("a", encoding="utf-8") as f:
                f.write("".join(line + "\n" for line in bad))
            if sys.platform != "win32":
                bak.chmod(0o600)
        except OSError as exc:
            log.exception("okunamayan geçmiş satırları yedeklenemedi: %s", bak)
            raise HistoryError(
                f"Okunamayan geçmiş satırları yedeklenemedi ({bak}): {exc}. Diskte yer "
                "olduğunu ve klasöre yazma izniniz olduğunu kontrol edin."
            ) from exc
        log.warning("%d okunamayan geçmiş satırı %s dosyasına yedeklendi", len(bad), bak)

    def _remove(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            log.exception("geçmiş dosyası silinemedi: %s", path)
            raise HistoryError(
                f"Geçmiş dosyası silinemedi ({path}): {exc}. Dosyayı elle silin veya "
                "klasöre yazma izniniz olduğunu kontrol edin."
            ) from exc

    def _write(self, sessions: tuple[Session, ...]) -> None:
        """Geçmişi tek seferde ve atomik olarak yazar (yarım dosya kalmaz)."""
        self._backup_bad_lines()
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
        stamp = self._stamp()
        self._cache = _Parsed(stamp, sessions, ()) if stamp is not None else None
