from dikte.text.commands import apply_commands, is_undo_command


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


def test_delete_last_sentence_when_command_is_its_own_sentence():
    text = "Merhaba. Bugün hava güzel. Son cümleyi sil. Yarın görüşürüz."
    assert apply_commands(text) == "Merhaba. Yarın görüşürüz."


def test_delete_last_sentence_after_time_keeps_prior_sentence():
    # "14.30." içindeki son nokta cümle sonudur; ilk nokta (rakamlar arası) değildir.
    assert apply_commands("Saat 14.30. Bu gitsin son cümleyi sil") == "Saat 14.30."


def test_delete_last_sentence_decimal_is_not_a_boundary():
    assert apply_commands("Kalsın. Oran 3.5 oldu son cümleyi sil") == "Kalsın."


def test_delete_last_sentence_after_number_ending_sentence():
    assert apply_commands("Madde 3. Bu gitsin son cümleyi sil") == "Madde 3."


def test_delete_last_sentence_ordinal_is_not_a_boundary():
    # "3. madde" sıra sayısıdır: rakamdan sonraki nokta küçük harfle devam ediyorsa
    # cümle bitmemiştir; silinen cümle "Toplam 3. madde önemli" olur.
    text = "Giriş yaptım. Toplam 3. madde önemli son cümleyi sil"
    assert apply_commands(text) == "Giriş yaptım."


def test_delete_last_word():
    assert apply_commands("merhaba dünya son kelimeyi sil gezegen") == "merhaba gezegen"


def test_delete_last_word_with_trailing_punctuation():
    assert apply_commands("Merhaba dünya. Son kelimeyi sil.") == "Merhaba"
    assert apply_commands("Merhaba dünya, son kelimeyi sil") == "Merhaba"


def test_delete_last_word_capitalizes_after_sentence_end():
    assert apply_commands("Bir. İki son kelimeyi sil üç") == "Bir. Üç"


def test_delete_last_word_at_start():
    assert apply_commands("Son kelimeyi sil merhaba") == "Merhaba"


def test_delete_commands_apply_left_to_right():
    # Önce cümle silinir ("Üç"), sonra kalan metnin son kelimesi ("iki.").
    assert apply_commands("Bir iki. Üç son cümleyi sil son kelimeyi sil") == "Bir"


def test_is_undo_command_whole_utterance_only():
    assert is_undo_command("geri al")
    assert is_undo_command("  Geri al. ")
    assert is_undo_command("GERİ AL!")
    assert is_undo_command("GERI AL,")
    assert is_undo_command("gerı al")
    assert not is_undo_command("parayı geri al")
    assert not is_undo_command("geri alındı")
    assert not is_undo_command("")
