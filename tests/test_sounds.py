import numpy as np

from dikte.core.state import DictationState
from dikte.ui.sounds import SoundPlayer, tone


def test_tone_has_expected_length_and_amplitude():
    t = tone(880.0, 90, 16000)
    assert t.dtype == np.float32 and len(t) == 1440 and np.abs(t).max() <= 0.21


def test_state_transitions_play_start_and_stop():
    played = []
    p = SoundPlayer(player=lambda d, sr: played.append((len(d), sr)))
    p.on_state(DictationState.RECORDING)
    p.on_state(DictationState.TRANSCRIBING)
    p.on_state(DictationState.CORRECTING)
    assert len(played) == 2 and all(sr == 16000 for _, sr in played)


def test_error_plays_error_sound_and_disabled_is_silent():
    played = []
    p = SoundPlayer(player=lambda d, sr: played.append(1))
    p.on_error("x")
    assert played == [1]
    p.set_enabled(False)
    p.on_error("x")
    p.on_state(DictationState.RECORDING)
    assert played == [1]


def test_player_failure_is_logged_once(caplog):
    def boom(d, sr):
        raise RuntimeError("cihaz yok")

    p = SoundPlayer(player=boom)
    p.play("start")
    p.play("stop")
    assert caplog.text.count("cihaz yok") == 1
