from dikte.config import AppProfile
from dikte.text.profiles import match_profile

CODE = AppProfile(name="Kod", match="code")
TERMINAL = AppProfile(name="Terminal", match="windowsterminal")


def test_matches_by_substring_case_insensitive():
    assert match_profile((CODE,), "Code.exe") is CODE


def test_first_match_wins():
    other_code = AppProfile(name="İkinci", match="code")
    assert match_profile((CODE, other_code), "code.exe") is CODE


def test_no_match_returns_none():
    assert match_profile((CODE, TERMINAL), "explorer.exe") is None


def test_empty_match_never_matches():
    blank = AppProfile(name="Boş", match="")
    assert match_profile((blank,), "anything.exe") is None


def test_empty_exe_returns_none():
    assert match_profile((CODE,), "") is None
