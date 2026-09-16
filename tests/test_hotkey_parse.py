import pytest

from dikte.platform.hotkey_parse import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    HotkeyParseError,
    parse_hotkey,
)


def test_ctrl_alt_space():
    hk = parse_hotkey("ctrl+alt+space")
    assert hk.modifiers == MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
    assert hk.vk == 0x20 and hk.label == "Ctrl+Alt+Space"


def test_letters_and_function_keys():
    assert parse_hotkey("ctrl+shift+d").vk == ord("D")
    assert parse_hotkey("win+f9").vk == 0x78
    assert parse_hotkey("win+f9").modifiers & MOD_WIN


def test_case_and_whitespace_insensitive():
    assert parse_hotkey(" CTRL + Alt + Space ") == parse_hotkey("ctrl+alt+space")


def test_requires_at_least_one_modifier():
    with pytest.raises(HotkeyParseError):
        parse_hotkey("space")


def test_unknown_key_raises():
    with pytest.raises(HotkeyParseError):
        parse_hotkey("ctrl+bogus")


def test_shift_modifier_bit_present():
    assert parse_hotkey("ctrl+shift+d").modifiers & MOD_SHIFT
    assert parse_hotkey("alt+f4").modifiers & MOD_ALT


def test_bare_key_rejected_by_default():
    with pytest.raises(HotkeyParseError):
        parse_hotkey("escape")


def test_bare_key_allowed_when_requested():
    spec = parse_hotkey("escape", allow_bare=True)
    assert spec.vk == 0x1B and spec.label == "Escape"


def test_bare_modifier_still_rejected():
    with pytest.raises(HotkeyParseError):
        parse_hotkey("ctrl", allow_bare=True)


def test_to_key_sequence_round_trips():
    from dikte.platform.hotkey_parse import from_key_sequence, to_key_sequence

    seq = to_key_sequence("ctrl+alt+space")
    assert seq.toString() == "Ctrl+Alt+Space"
    assert from_key_sequence(seq) == "ctrl+alt+space"


def test_from_key_sequence_lowercases():
    from PySide6.QtGui import QKeySequence

    from dikte.platform.hotkey_parse import from_key_sequence

    assert from_key_sequence(QKeySequence("Ctrl+Shift+D")) == "ctrl+shift+d"


def test_from_key_sequence_rejects_bare_key():
    from PySide6.QtGui import QKeySequence

    from dikte.platform.hotkey_parse import from_key_sequence

    with pytest.raises(HotkeyParseError):
        from_key_sequence(QKeySequence("D"))


def test_from_empty_sequence_raises():
    from PySide6.QtGui import QKeySequence

    from dikte.platform.hotkey_parse import from_key_sequence

    with pytest.raises(HotkeyParseError):
        from_key_sequence(QKeySequence())


def test_to_key_sequence_rejects_invalid_spec():
    from dikte.platform.hotkey_parse import to_key_sequence

    with pytest.raises(HotkeyParseError):
        to_key_sequence("ctrl+")


def test_register_rejects_bare_key_by_default():
    """Kullanıcı kısayolu en az bir değiştirici istemeli; 'a' tek başına kaydedilmemeli."""
    from dikte.platform.hotkey import GlobalHotkey

    assert GlobalHotkey().register("a") is False


def test_register_allows_bare_key_when_explicitly_permitted(monkeypatch):
    """İptal kısayolu (Esc) uygulamanın kendi ürettiği kısayoldur; çıplak tuşa izin verilir."""
    from dikte.platform import hotkey as hotkey_mod

    seen = []

    def spy(spec, *, allow_bare=False):
        seen.append(allow_bare)
        return parse_hotkey(spec, allow_bare=allow_bare)

    monkeypatch.setattr(hotkey_mod, "parse_hotkey", spy)
    hotkey_mod.GlobalHotkey().register("escape", allow_bare=True)
    assert seen == [True]
