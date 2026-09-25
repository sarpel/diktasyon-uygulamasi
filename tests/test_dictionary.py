from dikte.config import DictionaryEntry
from dikte.text.dictionary import apply_rules, hotwords, prompt_terms

E = (
    DictionaryEntry(term="Kubernetes", wrong=("kuber netes", "kübernetes")),
    DictionaryEntry(term="Sarp"),
)


def test_apply_rules_replaces_whole_words_case_insensitively():
    assert apply_rules("Kuber netes kümesi ve KÜBERNETES", E) == "Kubernetes kümesi ve Kubernetes"


def test_apply_rules_does_not_touch_substrings():
    assert apply_rules("sarpel", E) == "sarpel"


def test_hotwords_and_prompt_terms():
    assert hotwords(E) == "Kubernetes, Sarp"
    assert prompt_terms(E) == "Terimler: Kubernetes, Sarp"
    assert prompt_terms(()) == "" and hotwords(()) == ""


def test_prompt_terms_respects_limit():
    many = tuple(DictionaryEntry(term=f"terim{i}") for i in range(200))
    assert len(prompt_terms(many, max_chars=100)) <= 100


def test_apply_rules_is_idempotent_when_correct_term_already_present():
    entries = (DictionaryEntry(term="Visual Studio Code", wrong=("visual studio",)),)
    assert apply_rules("Visual Studio Code açtım", entries) == "Visual Studio Code açtım"
    assert apply_rules("visual studio açtım", entries) == "Visual Studio Code açtım"


def test_apply_rules_does_not_chain_entries():
    entries = (
        DictionaryEntry(term="React", wrong=("reakt",)),
        DictionaryEntry(term="React Native", wrong=("React",)),
    )
    assert apply_rules("React Native kullanıyorum", entries) == "React Native kullanıyorum"
    assert apply_rules("reakt ve React", entries) == "React ve React Native"


def test_apply_rules_prefers_longest_variant():
    entries = (
        DictionaryEntry(term="Go", wrong=("gou",)),
        DictionaryEntry(term="GoLand", wrong=("gou land",)),
    )
    assert apply_rules("gou land ve gou", entries) == "GoLand ve Go"


def test_apply_rules_turkish_dotted_i_variants():
    entries = (DictionaryEntry(term="Kubernetes", wrong=("kübernetıs",)),)
    text = "kübernetıs, KÜBERNETIS ve KÜBERNETİS"
    assert apply_rules(text, entries) == "Kubernetes, Kubernetes ve Kubernetes"


def test_apply_rules_term_is_literal_not_template():
    entries = (DictionaryEntry(term=r"C:\1\g<0>", wrong=("ce yol",)),)
    assert apply_rules("ce yol", entries) == r"C:\1\g<0>"


def test_apply_compiled_accepts_empty_rules():
    from dikte.text.dictionary import apply_compiled

    assert apply_compiled("metin", []) == "metin"
