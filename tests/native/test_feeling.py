"""Tone by meaning (luna/core/feeling.py), with a toy embedder: every example sentence points along the axis of its tone, so the logic
(thresholds, everyday talk, failure, no model) is tested without a real model. The real thresholds are guesses: tools/feeling_check.py."""
import math
import time

import pytest

from luna.core import character, feeling, memory_store

TONES = list(feeling.EXAMPLES) + ['']
AXIS = {tone: i for i, tone in enumerate(TONES)}
OF = {p: tone for tone, phrases in {**feeling.EXAMPLES, '': feeling.EVERYDAY}.items() for p in phrases}
MESSAGES = {}   # test message -> {axis: weight}


def toy(text):
    vec = [0.0] * (len(TONES) + 1)
    if text in OF:
        vec[AXIS[OF[text]]] = 1.0
    elif text in MESSAGES:
        for axis, w in MESSAGES[text].items():
            vec[AXIS[axis]] = w
    else:
        vec[-1] = 1.0   # something unrelated to every tone
    vec[-1] += 0.01
    return vec


@pytest.fixture
def model(tmp_path):
    memory_store.configure_cache(None)
    memory_store.set_embedder('toy', toy)
    feeling.reset()
    feeling.warm('toy')
    for _ in range(100):
        if 'toy' in feeling._pool:
            break
        time.sleep(0.05)
    yield
    memory_store.set_embedder(None, None)
    feeling.reset()


def say(text, **axes):
    MESSAGES[text] = axes
    return feeling.classify(text)


def test_nothing_without_a_real_model():
    memory_store.set_embedder(None, None)
    feeling.reset()
    assert feeling.classify('I feel so down today') == ''


def test_clear_meaning_gives_the_tone(model):
    assert say('my week was awful and I cannot stop crying', sad=1.0) == 'sad'
    assert say('this really makes me furious', angry=1.0, **{'': 0.2}) == 'angry'


def test_mixed_with_everyday_talk_is_not_a_feeling(model):
    assert say('could you maybe check the weather, a bit sad though', sad=0.5, **{'': 0.6}) == ''
    assert say('open the browser please', **{'': 1.0}) == ''


def test_unrelated_text_gives_nothing(model):
    assert feeling.classify('some entirely unrelated sentence here') == ''


def test_length_limits(model):
    assert feeling.classify('sad') == '' and feeling.classify('x ' * 400) == ''


def test_rude_is_never_guessed():
    assert 'rude' not in feeling.EXAMPLES and 'sorry' not in feeling.EXAMPLES


def test_model_failure_is_quiet_and_backs_off(monkeypatch):
    calls = []

    def down(text):
        calls.append(text)
        raise OSError('ollama is down')
    memory_store.configure_cache(None)
    memory_store.set_embedder('down', down)
    feeling.reset()
    try:
        assert feeling.classify('I feel so down today') == ''
        time.sleep(0.3)   # the background warm-up fails and starts the cool-down
        assert feeling.classify('I feel so down today') == ''
        n = len(calls)
        assert feeling.classify('and one more sentence about sadness') == '' and len(calls) == n   # no hammering of a dead model
    finally:
        memory_store.set_embedder(None, None)
        feeling.reset()


def test_sense_uses_meaning_only_when_words_found_nothing(model):
    MESSAGES['honestly everything feels heavy lately'] = {'sad': 1.0}
    saved = {k: dict(character.MEMORY[k]) for k in ('mood', 'worry', 'sensed', 'hurt')}
    assert character.sense('honestly everything feels heavy lately') == 'sad'
    assert character.MEMORY['worry']['tone'] == 'sad'
    MESSAGES['спасибо большое, ты прелесть'] = {'angry': 1.0}   # the word list says thanks; meaning must not override it
    assert character.sense('спасибо большое, ты прелесть') == 'thanks'
    character.MEMORY.update(saved)
