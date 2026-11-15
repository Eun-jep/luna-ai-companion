"""Her face follows her words even when the model wrote no [emotion] tag - and never overrides one it did write."""
import json

import pytest

import app
from luna.core import replyfeel


@pytest.mark.parametrize('text,emotion', [
    ('Спасибо, мне очень приятно!', 'happy'),
    ('Прости, что так вышло.', 'sad'),
    ('Ого, вот это новость!', 'surprised'),
    ("I'm so sorry about that.", 'sad'),
    ('Thank you for telling me.', 'happy'),
    ('Я тебя люблю, правда.', 'love'),
    ('Не понимаю, о чём ты.', 'confused'),
    ('고마워요, 정말 기뻐요.', 'happy'),
])
def test_clear_words_give_an_emotion(text, emotion):
    assert replyfeel.infer(text) == emotion


@pytest.mark.parametrize('text', ['Вот список дел на сегодня.', 'Файл лежит на рабочем столе.', 'The result is 42.', '', 'ок'])
def test_plain_speech_stays_untouched(text):
    assert replyfeel.infer(text) is None


def test_a_tag_from_the_model_always_wins():
    assert replyfeel.tag_for('[sad] Спасибо!', 'Спасибо!', seen=False) == ''
    assert replyfeel.tag_for('Спасибо!', 'Спасибо!', seen=True) == ''
    assert replyfeel.tag_for('Спасибо!', 'Спасибо!', seen=False) == '[happy]'
    assert replyfeel.tag_for('[wave] Привет', 'Привет', seen=False) == ''   # a gesture is not an emotion


def run_turn(reply):
    saved = app.generate_stream
    app.generate_stream = lambda *a, **k: iter([reply])
    try:
        events = [e if isinstance(e, dict) else json.loads(e) for e in app.chat_turn({'message': 'привет', 'history': []})]
    finally:
        app.generate_stream = saved
    return [e['script'] for e in events if 'script' in e]


def test_the_engine_fills_in_the_missing_tag():
    scripts = run_turn('Спасибо, что пришёл! Расскажи, как прошёл день.')
    assert scripts and scripts[0].startswith('[happy]')


def test_the_engine_leaves_the_models_own_tags_alone():
    scripts = run_turn('[sad] Спасибо, что пришёл! Расскажи, как прошёл день.')
    assert scripts and '[happy]' not in ' '.join(scripts)
