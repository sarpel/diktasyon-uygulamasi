import json

from dikte.llm.jsontext import extract_json_object


def test_plain_object_is_returned_unchanged():
    assert extract_json_object('{"a": 1}') == '{"a": 1}'


def test_strips_think_block_even_if_it_contains_braces():
    out = extract_json_object('<think>önce {"a": 0} düşündüm</think>{"a": 1}')
    assert json.loads(out) == {"a": 1}


def test_strips_code_fence():
    assert json.loads(extract_json_object('```json\n{"a": 1}\n```')) == {"a": 1}


def test_extracts_outermost_object_from_surrounding_prose():
    out = extract_json_object('Tabii: {"a": {"b": 2}} umarım {olur}')
    assert json.loads(out) == {"a": {"b": 2}}


def test_skips_brace_noise_before_the_object():
    assert json.loads(extract_json_object('not {x} → {"a": 1}')) == {"a": 1}


def test_returns_cleaned_text_when_no_object():
    assert extract_json_object("<think>x</think> düz metin ") == "düz metin"
