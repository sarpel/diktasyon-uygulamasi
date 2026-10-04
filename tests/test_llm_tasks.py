import json

import pytest

from dikte.llm.provider import LlmError
from dikte.llm.tasks import (
    CorrectionResult,
    correct,
    correction_looks_valid,
    enhance_prompt,
    translate,
)


class FakeProvider:
    name = "fake"

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def complete(self, system, user, *, json_schema=None, temperature=0.2):
        self.calls.append({"system": system, "user": user, "json_schema": json_schema})
        return self.reply


def test_correct_parses_json_reply():
    p = FakeProvider(
        json.dumps(
            {
                "corrected_text": "Bugün hava çok güzel.",
                "changes": [{"original": "hava çuk", "replacement": "hava çok", "reason": "yazım"}],
            }
        )
    )
    res = correct(p, "bugün hava çuk güzel")
    assert isinstance(res, CorrectionResult)
    assert res.corrected_text == "Bugün hava çok güzel."
    # LLM'in gönderdiği changes yok sayılır; liste difflib ile hesaplanır. İlk değişiklik
    # cümle başı büyük harfi ("bugün" -> "Bugün"), asıl kelime düzeltmesi ikinci sırada.
    assert res.changes[1].replacement == "çok"
    assert res.changes[1].original == "çuk"
    assert p.calls[0]["json_schema"] is not None
    assert "bugün hava çuk güzel" in p.calls[0]["user"]


def test_correct_empty_input_returns_empty_without_calling_llm():
    p = FakeProvider("ignored")
    res = correct(p, "   ")
    assert res.corrected_text == "" and res.changes == () and p.calls == []


def test_correct_invalid_json_raises_llm_error():
    with pytest.raises(LlmError):
        correct(FakeProvider("not json"), "merhaba")


def test_correct_appends_glossary_to_system():
    p = FakeProvider(json.dumps({"corrected_text": "Merhaba."}))
    correct(p, "merhaba", glossary="Sözlük: X")
    assert "Sözlük: X" in p.calls[0]["system"]


def test_correct_tolerates_missing_changes():
    res = correct(FakeProvider(json.dumps({"corrected_text": "Merhaba."})), "merhaba")
    assert res.changes[0].reason == "noktalama/büyük harf"


def test_translate_returns_stripped_text():
    p = FakeProvider("  Hello world.  ")
    assert translate(p, "Merhaba dünya.") == "Hello world."
    assert "English" in p.calls[0]["system"]


def test_enhance_prompt_returns_text_and_uses_english_system_prompt():
    p = FakeProvider("# Goal\nBuild X")
    out = enhance_prompt(p, "bana bir todo uygulaması yaz")
    assert out.startswith("# Goal")
    assert "AI agent" in p.calls[0]["system"]


# ---- JSON çıkarımı, kesilme, gizlilik, akıl sağlığı denetimi


def test_correct_extracts_json_from_think_block_and_code_fence():
    reply = (
        '<think>{"corrected_text": "yanlış"}</think>\n```json\n{"corrected_text": "Merhaba."}\n```'
    )
    assert correct(FakeProvider(reply), "merhaba").corrected_text == "Merhaba."


def test_invalid_json_error_message_does_not_contain_reply_text():
    with pytest.raises(LlmError) as info:
        correct(FakeProvider("gizli dikte içeriği burada"), "gizli dikte içeriği burada")
    assert "gizli" not in str(info.value)


def test_correction_looks_valid_accepts_similar_length():
    assert correction_looks_valid("bir iki üç dört beş", "Bir, iki, üç, dört, beş.")


def test_correction_looks_valid_rejects_summary_and_expansion():
    raw = "bir iki üç dört beş altı yedi sekiz dokuz on"
    assert not correction_looks_valid(raw, "bir iki üç dört")  # 0.4×
    assert not correction_looks_valid(raw, " ".join(["kelime"] * 17))  # 1.7×
    assert correction_looks_valid(raw, "bir iki üç dört beş")  # 0.5× sınırda
    assert correction_looks_valid(raw, " ".join(["kelime"] * 16))  # 1.6× sınırda


def test_short_raw_rejects_chatty_reply():
    # "nasılsın" dikte edildi; model soruyu yanıtladı — yapıştırılmamalı.
    assert not correction_looks_valid(
        "nasılsın", "İyiyim, teşekkür ederim! Size nasıl yardımcı olabilirim?"
    )
    assert not correction_looks_valid("bir iki üç", "Tamam, bunu yapabilirim ve çok daha fazlası.")


def test_short_raw_allows_up_to_two_extra_words():
    assert correction_looks_valid("nasılsın", "Nasılsın?")
    assert correction_looks_valid("nul pointer hatası", "Null pointer hatası.")
    assert correction_looks_valid("jason", "JSON")
    assert correction_looks_valid("nasılsın", "nasılsın bir iki")  # +2 sınırda
    assert not correction_looks_valid("nasılsın", "nasılsın bir iki üç")  # +3


def test_empty_correction_is_allowed():
    # Model anlamsız ses parçalarında boş döndürebilir; denetleyici ham metne döner.
    assert correction_looks_valid("ıı hmm şey", "")


def test_rejects_reply_with_little_content_overlap():
    raw = "bugün toplantıda bütçe planını ve yeni işe alımları konuştuk"
    reply = "Harika, toplantının verimli geçtiğine sevindim; başka bir isteğiniz olursa söyleyin."
    assert not correction_looks_valid(raw, reply)


def test_overlap_is_turkish_case_aware():
    raw = "istanbul ve ankara ofisleri yarın kapalı ıspanak alırım"
    assert correction_looks_valid(raw, "İSTANBUL VE ANKARA OFİSLERİ YARIN KAPALI, ISPANAK ALIRIM.")


_REALISTIC = [
    ("bugün hava çuk güzel dışarı çıkalım mı", "Bugün hava çok güzel, dışarı çıkalım mı?"),
    ("yarın sabah erken kalk mam gerekiyor", "Yarın sabah erken kalkmam gerekiyor."),
    ("şu dosyayı bana ma il atar mısın", "Şu dosyayı bana mail atar mısın?"),
    ("bu sabah çok yoğun bi gün oldu", "Bu sabah çok yoğun bir gün oldu."),
    ("sunucu çöktü ğü için istekler zaman aşımına uğradı", "Sunucu çöktüğü için istekler."),
    (
        "kredi kartı extra sini bu ay ödemeyi unuttum",
        "Kredi kartı ekstresini bu ay ödemeyi unuttum.",
    ),
    (
        "faster whisper modelini large turbo ya güncelle",
        "faster-whisper modelini large-v3-turbo'ya güncelle",
    ),
    (
        "docker kompoz dosyasında port çakışması var",
        "Docker Compose dosyasında port çakışması var.",
    ),
    (
        "projeyi git hapa pushladım pull rikuest açar mısın",
        "Projeyi GitHub'a pushladım, PR açar mısın?",
    ),
    ("postgre sql veri tabanına indeks ekleyelim", "PostgreSQL veritabanına indeks ekleyelim."),
    (
        "jason dosyasındaki alanları şemaya göre doğrula",
        "JSON dosyasındaki alanları şemaya göre doğrula.",
    ),
    ("ali ahmet ve mehmet toplantıya katılacak", "Ali, Ahmet ve Mehmet toplantıya katılacak."),
    (
        "Testler yerelde geçiyor ama CI'da başarısız oluyor.",
        "Testler yerelde geçiyor ama CI'da başarısız.",
    ),
    (
        "ee bugün şey yapacağız hani şu kubernetis clusterını bir de bir de "
        "yüzde yirmi küçülteceğiz",
        "Bugün şu Kubernetes cluster'ını %20 küçülteceğiz.",
    ),
    (
        "toplantı iki bin yirmi altı ocak ayında üç buçuk saat sürdü çok verimliydi",
        "Toplantı 2026 Ocak ayında 3,5 saat sürdü, çok verimliydi.",
    ),
]


@pytest.mark.parametrize(("raw", "corrected"), _REALISTIC)
def test_realistic_corrections_pass_sanity_check(raw, corrected):
    assert correction_looks_valid(raw, corrected)


def test_correct_raises_on_short_chatty_reply():
    reply = json.dumps(
        {"corrected_text": "İyiyim, teşekkür ederim! Size nasıl yardımcı olabilirim?"}
    )
    with pytest.raises(LlmError) as info:
        correct(FakeProvider(reply), "nasılsın")
    assert "nasılsın" not in str(info.value)


def test_correct_raises_on_low_overlap_reply():
    raw = "bugün toplantıda bütçe planını ve yeni işe alımları konuştuk"
    reply = json.dumps(
        {"corrected_text": "Harika, verimli geçtiğine sevindim; başka isteğiniz var mı?"}
    )
    with pytest.raises(LlmError) as info:
        correct(FakeProvider(reply), raw)
    assert "bütçe" not in str(info.value)


# ---- çeviri ve prompt iyileştirme korumaları


def test_translate_rejects_empty_reply():
    with pytest.raises(LlmError, match="boş"):
        translate(FakeProvider("   "), "Merhaba dünya.")


def test_translate_rejects_runaway_reply():
    with pytest.raises(LlmError, match="Çeviri") as info:
        translate(FakeProvider("word " * 400), "Merhaba dünya.")
    assert "Merhaba" not in str(info.value)


def test_translate_allows_normal_expansion():
    assert translate(FakeProvider("Okay, sure thing."), "Tamam.") == "Okay, sure thing."
    long_tr = "Bu çok uzun bir Türkçe cümle. " * 20
    assert translate(FakeProvider("This is a very long English sentence. " * 25), long_tr)


def test_enhance_prompt_rejects_empty_reply():
    with pytest.raises(LlmError, match="boş"):
        enhance_prompt(FakeProvider(""), "bana bir todo uygulaması yaz")


def test_enhance_prompt_allows_large_expansion_but_not_runaway():
    short = "bana bir todo uygulaması yaz"
    assert enhance_prompt(FakeProvider("# Goal\n" + "x" * 3000), short)
    with pytest.raises(LlmError, match="Prompt"):
        enhance_prompt(FakeProvider("x" * 50_000), short)


def test_correct_raises_when_sanity_check_fails(caplog):
    raw = "bugün toplantıda bütçe planını ve yeni işe alımları konuştuk"
    p = FakeProvider(json.dumps({"corrected_text": "Tabii."}))
    with pytest.raises(LlmError, match="kelime") as info:
        correct(p, raw)
    assert "bütçe" not in str(info.value)
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_correct_skips_sanity_check_when_disabled():
    raw = "bugün toplantıda bütçe planını ve yeni işe alımları konuştuk"
    p = FakeProvider(json.dumps({"corrected_text": "Tabii."}))
    assert correct(p, raw, sanity_check=False).corrected_text == "Tabii."
