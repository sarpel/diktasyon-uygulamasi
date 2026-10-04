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


def test_exact_exe_stem_beats_earlier_substring_match():
    vscode = AppProfile(name="VS Code", match="vscode")
    codex = AppProfile(name="Codex", match="codex")
    assert match_profile((CODE, codex), "codex.exe") is codex
    assert match_profile((CODE, vscode), "vscode") is vscode


def test_longest_substring_match_wins():
    terminal = AppProfile(name="Term", match="terminal")
    gnome = AppProfile(name="Gnome", match="gnome-terminal")
    assert match_profile((terminal, gnome), "gnome-terminal-server") is gnome


def test_exact_match_is_case_insensitive_and_ignores_exe_suffix():
    upper = AppProfile(name="Kod", match="Code")
    assert match_profile((AppProfile(name="X", match="cod"), upper), "CODE.EXE") is upper


def test_match_with_exe_suffix_matches_stem_foreground_name():
    # Ön plan yoklayıcısı ".exe"siz kök döndürür; profil "KeePass.exe" diye yazılmış olabilir.
    keepass = AppProfile(name="KeePass", match="KeePass.exe")
    assert match_profile((keepass,), "keepass") is keepass
    assert match_profile((keepass,), "KeePass.exe") is keepass


def test_match_with_exe_suffix_still_matches_by_substring():
    code = AppProfile(name="Kod", match="Code.exe")
    assert match_profile((code,), "vscode") is code
    assert match_profile((code,), "explorer") is None


def test_exe_suffix_profile_exact_stem_beats_longer_substring():
    code = AppProfile(name="Kod", match="Code.exe")
    vscode = AppProfile(name="VS Code", match="vscode")
    assert match_profile((vscode, code), "code") is code
