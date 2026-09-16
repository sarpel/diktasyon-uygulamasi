from __future__ import annotations

from collections.abc import Sequence

from dikte.config import AppProfile


def match_profile(profiles: Sequence[AppProfile], exe: str) -> AppProfile | None:
    """`exe` (küçük harf süreç adı) içinde `match` alt dizesi geçen ilk profili döndürür."""
    if not exe:
        return None
    for profile in profiles:
        if profile.match and profile.match.lower() in exe.lower():
            return profile
    return None
