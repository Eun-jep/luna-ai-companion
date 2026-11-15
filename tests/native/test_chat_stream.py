"""The streaming engine (chat_turn): sentences cut from the model's text as it arrives, stage directions kept apart from speech,
code kept out of the voice, history written once at the end. The model is replaced by a fake that yields the chunks we choose."""
import pytest

import app
from luna.core.character import HISTORY, MEMORY

REPLY = '[happy] Привет! Я тебя слышу. [nod] Расскажи, как прошёл твой день сегодня?'


@pytest.fixture
def engine(monkeypatch):
    """-> run(chunks, **data): the events of one turn, with a clean history and no network."""
    monkeypatch.setattr(app, 'generate', lambda *a, **k: '')
    monkeypatch.setattr(app, 'refresh_summary', lambda *a, **k: None)
    saved = list(HISTORY)
    HISTORY.clear()

    def run(chunks, **data):
        monkeypatch.setattr(app, 'generate_stream', lambda *a, **k: iter(chunks))
        return list(app.chat_turn(dict({'message': 'привет', 'history': []}, **data)))
    yield run
    HISTORY[:] = saved


def sentences(events):
    return [e['answer'] for e in events if 'answer' in e]


def chunked(text, size):
    return [text[i:i + size] for i in range(0, len(text), size)]


def test_a_reply_is_cut_into_sentences_with_directions_kept_apart(engine):
    events = engine([REPLY])
    assert sentences(events) == ['Привет! Я тебя слышу.', 'Расскажи, как прошёл твой день сегодня?']   # a piece under MIN_CHUNK joins the next sentence
    scripts = [e['script'] for e in events if 'script' in e]
    assert scripts[0].startswith('[happy]')
    assert any('[nod]' in s for s in scripts)
    assert not any('[' in a for a in sentences(events))   # no direction is ever spoken


@pytest.mark.parametrize('size', [1, 2, 3, 5, 7, 13])
def test_where_the_chunks_break_does_not_change_the_result(engine, size):
    whole = engine([REPLY])
    pieces = engine(chunked(REPLY, size))   # a chunk may end inside a word, inside [happy], anywhere
    assert sentences(pieces) == sentences(whole)
    assert [e['script'] for e in pieces if 'script' in e] == [e['script'] for e in whole if 'script' in e]


def test_a_direction_alone_waits_for_the_next_sentence(engine):
    events = engine(['Хорошо, договорились. ', '[shy] ', 'Тогда до завтра, мой друг.'])
    scripts = [e['script'] for e in events if 'script' in e]
    assert sentences(events)[-1].startswith('Тогда до завтра')
    assert '[shy]' in scripts[-1]


def test_code_is_shown_but_never_spoken(engine):
    events = engine(['Вот пример. ```python\nprint(1)\n``` Теперь ты знаешь, как это делается.'])
    assert [e['code']['lang'] for e in events if 'code' in e] == ['python']
    assert not any('print' in a for a in sentences(events))
    assert any('Теперь ты знаешь' in a for a in sentences(events))


def test_the_turn_ends_with_done_and_a_mood(engine):
    events = engine([REPLY])
    assert events[-1].get('done') is True and 'mood' in events[-1]


def test_history_gets_his_message_and_her_reply_once(engine):
    engine([REPLY])
    assert [m['role'] for m in HISTORY] == ['user', 'assistant']
    assert HISTORY[0]['content'] == 'привет'
    assert 'Я тебя слышу' in HISTORY[1]['content']


def test_an_empty_reply_is_an_error_not_silence(engine):
    with pytest.raises(RuntimeError):
        engine([''])
    assert HISTORY == []   # nothing is remembered of a turn that produced nothing


def test_quiet_means_she_says_nothing_and_remembers_nothing(engine):
    events = engine(['[quiet]'], initiative='screen', image='data:image/jpeg;base64,AAAA')
    assert events == [{'done': True, 'quiet': True, 'mood': events[0]['mood']}]
    assert HISTORY == []


def test_a_turn_counts_in_her_memory(engine):
    before = MEMORY['turns']
    engine([REPLY])
    assert MEMORY['turns'] == before + 1


def test_her_own_initiative_does_not_count_as_his_turn(engine):
    before = MEMORY['turns']
    engine(['Привет, я тут подумала о тебе.'], initiative='idle')
    assert MEMORY['turns'] == before


def test_bad_input_is_refused_before_the_model_is_asked(engine):
    for bad in ('', '   ', 'x' * 20000):
        with pytest.raises(ValueError):
            engine([REPLY], message=bad)
