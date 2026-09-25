from __future__ import annotations

from collections.abc import Sequence

from dikte.config import AppProfile


def _exe_stem(exe: str) -> str:
    name = exe.strip().lower()
    return name.removesuffix(".exe")


def match_profile(profiles: Sequence[AppProfile], exe: str) -> AppProfile | None:
    """`exe` (süreç adı) için profil seçer. Önce `match` süreç adının kökü ile birebir
    aynı (".exe" hariç, büyük/küçük harf duyarsız) ilk profil; yoksa `match` alt dizesi
    olarak geçen profillerden en uzun `match`e sahip olanı (eşitlikte ilki) döner. Böylece
    "code" profili "codex" veya "vscode" için ayrıca tanımlanmış profilin önüne geçmez."""
    stem = _exe_stem(exe)
    if not stem:
        return None
    candidates = [p for p in profiles if p.match and p.match.lower() in exe.lower()]
    for profile in candidates:
        if _exe_stem(profile.match) == stem:
            return profile
    return max(candidates, key=lambda p: len(p.match), default=None)
