from dikte.text.commands import apply_commands


def test_new_line_and_paragraph():
    assert apply_commands("merhaba yeni satır nasılsın") == "merhaba\nNasılsın"
    assert apply_commands("Birinci. Yeni paragraf ikinci") == "Birinci.\n\nİkinci"


def test_delete_last_sentence():
    assert apply_commands("Bu kalsın. Bu gitsin son cümleyi sil devam") == "Bu kalsın. Devam"


def test_plain_text_untouched():
    assert apply_commands("bu nokta önemli") == "bu nokta önemli"


def test_commands_are_case_insensitive():
    assert apply_commands("merhaba YENİ SATIR nasılsın") == "merhaba\nNasılsın"


def test_delete_last_sentence_at_start_has_no_prior_sentence():
    assert apply_commands("son cümleyi sil merhaba") == "Merhaba"


def test_delete_last_sentence_at_end_leaves_prior_sentence():
    assert apply_commands("Bu kalsın. Bu gitsin son cümleyi sil") == "Bu kalsın."
