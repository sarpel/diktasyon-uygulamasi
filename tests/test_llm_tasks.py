import json

import pytest

from dikte.llm.provider import LlmError
from dikte.llm.tasks import CorrectionResult, correct, enhance_prompt, translate


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
