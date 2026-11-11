"""Praise of her (convo.COMPLIMENT) in ru/en/ko/ja: a warm, human-reply hint; silent on ordinary talk and on plain thanks."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import convo
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

MARK = 'Он хвалит тебя саму'
for ph in ['ты такая умная', 'ты классная', 'ты правда очень красивая', 'ты просто чудо', 'мне нравится с тобой общаться', 'рад, что ты есть',
           "you're so smart", 'you are awesome', "you're such a sweet", 'I really enjoy talking to you', "I'm glad you're here",
           '너 정말 똑똑해', '너 진짜 귀여워', '너랑 얘기하는 게 좋아', '네가 있어서 다행이야', 'あなたは本当に賢い', '君って優しい', 'あなたと話すのが好き', '君がいてくれてよかった']:
    ok('compliment: ' + ph, MARK in str(convo.hints([], ph, pick=lambda r: list(r)[0])))
for ph in ['ты где?', 'как дела', 'спасибо', 'you are late', "you're welcome", 'I like pizza', '너 어디야', 'あなたは誰', 'ты уже ответила на вопрос?',
           'умная колонка не включается', 'ты такая же, как раньше?']:
    ok('no praise hint: ' + ph, MARK not in str(convo.hints([], ph, pick=lambda r: list(r)[0])))
ok('hint forbids the canned refusal', 'всего лишь программа' in str(convo.hints([], 'ты классная', pick=lambda r: list(r)[0])))
