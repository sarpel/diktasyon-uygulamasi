from __future__ import annotations

from dataclasses import dataclass

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x0008, 0x4000

_MODS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "meta": MOD_WIN,
}
_MOD_LABEL = {MOD_CONTROL: "Ctrl", MOD_ALT: "Alt", MOD_SHIFT: "Shift", MOD_WIN: "Win"}
_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "pause": 0x13,
    "scrolllock": 0x91,
    "capslock": 0x14,
    "numlock": 0x90,
    "printscreen": 0x2C,
    **{f"f{i}": 0x70 + i - 1 for i in range(1, 25)},
}


class HotkeyParseError(ValueError):
    pass


@dataclass(frozen=True)
class HotkeySpec:
    modifiers: int
    vk: int
    label: str


def parse_hotkey(spec: str) -> HotkeySpec:
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if len(parts) < 2:
        raise HotkeyParseError(
            "Kısayol en az bir değiştirici (Ctrl/Alt/Shift/Win) ve bir tuş içermeli"
        )
    *mods, key = parts
    modifiers = 0
    for m in mods:
        if m not in _MODS:
            raise HotkeyParseError(f"Bilinmeyen değiştirici: {m}")
        modifiers |= _MODS[m]
    if key in _KEYS:
        vk = _KEYS[key]
    elif len(key) == 1 and key.isalnum() and key.isascii():
        vk = ord(key.upper())
    else:
        raise HotkeyParseError(f"Bilinmeyen tuş: {key}")
    labels = [_MOD_LABEL[b] for b in (MOD_CONTROL, MOD_ALT, MOD_SHIFT, MOD_WIN) if modifiers & b]
    label = "+".join(labels + [key.capitalize() if len(key) > 1 else key.upper()])
    return HotkeySpec(modifiers | MOD_NOREPEAT, vk, label)
