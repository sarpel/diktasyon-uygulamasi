from dikte.llm.diff import Change, word_changes


def test_identical_text_has_no_changes():
    assert word_changes("hava çok güzel", "hava çok güzel") == ()


def test_replacement_reports_words_and_offsets():
    ch = word_changes("hava çuk güzel", "Hava çok güzel.")
    assert [c.reason for c in ch] == [
        "noktalama/büyük harf",
        "değiştirildi",
        "noktalama/büyük harf",
    ]
    mid = ch[1]
    assert (mid.original, mid.replacement) == ("çuk", "çok")
    assert "Hava çok güzel."[mid.start : mid.end] == "çok"


def test_insert_and_delete():
    ins = word_changes("yarın gel", "yarın erken gel")
    assert ins == (Change("", "erken", "eklendi", 6, 11),)
    dele = word_changes("yarın erken gel", "yarın gel")
    assert dele[0].reason == "silindi" and dele[0].start == dele[0].end


def test_multiword_replacement_is_one_change():
    ch = word_changes("docker kompoz dosyası", "docker compose dosyası")
    assert len(ch) == 1 and ch[0].original == "kompoz"


def test_change_defaults_keep_old_history_loadable():
    assert Change("a", "b", "r").start == -1
