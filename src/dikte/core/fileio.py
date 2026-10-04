"""Kişisel verileri (geçmiş, ayarlar, başarısız kayıt sesi) diske güvenli ve atomik yazma."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def write_private_atomic(path: Path, data: bytes) -> None:
    """`data`'yı `path`'e atomik olarak yazar; yarım dosya ya da geçici izin penceresi kalmaz.

    Geçici dosya hedefle aynı klasörde `mkstemp` ile oluşturulur: O_EXCL ile ve baştan
    0600 izniyle açılır (umask'a bağlı geniş izinle oluşturulup sonra daraltılmaz; Windows
    bu izni büyük ölçüde yok sayar). Veri `flush` + `os.fsync` ile diske indirildikten sonra
    `os.replace` ile yerine konur; güç kesilirse ya eski ya yeni içerik kalır. Hata olursa
    geçici dosya silinir ve `OSError` çağırana yükselir (kullanıcı mesajını çağıran üretir)."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            log.exception("geçici dosya silinemedi: %s", tmp)
        raise
