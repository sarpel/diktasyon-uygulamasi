from dikte.core.state import Session


def test_output_text_correct_mode_returns_corrected_text():
    s = Session(mode="correct", corrected_text="Merhaba.", translation="Hello.")
    assert s.output_text == "Merhaba."


def test_output_text_translate_mode_prefers_translation():
    s = Session(mode="translate", corrected_text="Merhaba.", translation="Hello.")
    assert s.output_text == "Hello."


def test_output_text_translate_mode_falls_back_when_no_translation_yet():
    s = Session(mode="translate", corrected_text="Merhaba.")
    assert s.output_text == "Merhaba."


def test_output_text_prompt_mode_prefers_enhanced_prompt():
    s = Session(mode="prompt", corrected_text="Merhaba.", enhanced_prompt="# Goal")
    assert s.output_text == "# Goal"


def test_output_text_prompt_mode_falls_back_when_no_prompt_yet():
    s = Session(mode="prompt", corrected_text="Merhaba.")
    assert s.output_text == "Merhaba."
