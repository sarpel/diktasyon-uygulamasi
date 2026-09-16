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
