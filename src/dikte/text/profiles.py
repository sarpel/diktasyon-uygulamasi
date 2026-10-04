"""Ön plandaki uygulamanın süreç adına göre uygulama profili seçimi."""

from __future__ import annotations

from collections.abc import Sequence

from dikte.config import AppProfile


def _exe_stem(exe: str) -> str:
    name = exe.strip().lower()
    return name.removesuffix(".exe")


def match_profile(profiles: Sequence[AppProfile], exe: str) -> AppProfile | None:
    """`exe` (süreç adı) için profil seçer. Önce `match` süreç adının kökü ile birebir
    aynı (her ikisinde de ".exe" hariç, büyük/küçük harf duyarsız) ilk profil; yoksa
    `match` kökü süreç adı kökünde alt dize olarak geçen profillerden en uzun `match`e
    sahip olanı (eşitlikte ilki) döner. Böylece
    "code" profili "codex" veya "vscode" için ayrıca tanımlanmış profilin önüne geçmez."""
    stem = _exe_stem(exe)
    if not stem:
        return None
    # Hem süreç adı hem `match` ".exe"siz köke indirgenir: yoklayıcı kök döndürürken
    # kullanıcı profili "KeePass.exe" diye yazmış olabilir.
    candidates = [(p, s) for p in profiles if (s := _exe_stem(p.match)) and s in stem]
    for profile, match_stem in candidates:
        if match_stem == stem:
            return profile
    best = max(candidates, key=lambda pair: len(pair[1]), default=None)
    return best[0] if best else None
