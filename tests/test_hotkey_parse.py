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
