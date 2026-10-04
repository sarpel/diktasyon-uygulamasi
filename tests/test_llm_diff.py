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
    assert ins == (Change("", "erken", "eklendi", 6, 11, 5, 5),)
    dele = word_changes("yarın erken gel", "yarın gel")
    assert dele[0].reason == "silindi" and dele[0].start == dele[0].end


def test_multiword_replacement_is_one_change():
    ch = word_changes("docker kompoz dosyası", "docker compose dosyası")
    assert len(ch) == 1 and ch[0].original == "kompoz"


def test_change_defaults_keep_old_history_loadable():
    assert Change("a", "b", "r").start == -1


def test_changes_carry_offsets_in_original_text():
    """git diff görünümü için silinen/değişen kelimenin ham metindeki yeri de bilinmeli."""
    raw = "hava çuk güzel"
    ch = word_changes(raw, "Hava çok güzel.")
    mid = ch[1]
    assert raw[mid.orig_start : mid.orig_end] == "çuk"
    assert raw[ch[0].orig_start : ch[0].orig_end] == "hava"


def test_deleted_words_have_original_range_and_empty_new_range():
    raw = "bugün ee toplantı var"
    ch = word_changes(raw, "bugün toplantı var")
    (deleted,) = ch
    assert deleted.reason == "silindi"
    assert raw[deleted.orig_start : deleted.orig_end] == "ee"
    assert deleted.start == deleted.end


def test_inserted_words_have_empty_original_range():
    raw = "toplantı var"
    ch = word_changes(raw, "yarın toplantı var")
    (inserted,) = ch
    assert inserted.reason == "eklendi"
    assert inserted.orig_start == inserted.orig_end
    assert "yarın toplantı var"[inserted.start : inserted.end] == "yarın"


def test_change_defaults_keep_old_records_valid():
    c = Change("a", "b", "değiştirildi", 0, 1)
    assert (c.orig_start, c.orig_end) == (-1, -1)
