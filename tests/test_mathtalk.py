"""Arithmetic in words (mathtalk.py): asked in ru, en, ko, ja; each number is checked against Python itself; silent on ordinary talk with numbers in it."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.skills import mathtalk
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)


def num(q):
    got = mathtalk.answer(q)
    return got[1].rsplit('= ', 1)[-1] if got else None


for q, want in [('сколько будет 17 умножить на 23', 17 * 23), ('what is 17 times 23', 17 * 23), ('17 곱하기 23은?', 17 * 23), ('17かける23は?', 17 * 23), ('17 x 23', 17 * 23),
                ('посчитай 15% от 2300', 345), ('how much is 15 percent of 80', 12), ('2300의 15%는?', 345), ('2300の15%は?', 345),
                ('square root of 144', 12), ('корень из 144 сколько', 12), ('144의 제곱근은?', 12), ('144の平方根は?', 12),
                ('сколько будет 2 в степени 10', 1024), ('what is 2 to the power of 10', 1024), ('12 плюс 30 минус 5 сколько будет', 37), ('9 더하기 16은 얼마야', 25), ('3足す4は?', 7),
                ('what is 100 divided by 8', 12.5), ('сколько будет (3+4)*5', 35), ('how much is 7 minus 10', -3), ('сколько будет 2,5 умножить на 4', 10), ('25 x 4 = ?', 100), ('10 나누기 4는?', 2.5), ('10割る4は?', 2.5)]:
    got = num(q)
    ok('%s = %s' % (q, want), got is not None and abs(float(got) - want) < 1e-9)
ok('a long division is shown with its digits', num('сколько будет 1000 разделить на 3').startswith('333.33'))

for q, frag in [('переведи 10 км в мили', '6.2137'), ('convert 100 F to C', '37.77'), ('5 фунтов в кг переведи', '2.2679'), ('what is 10 km in miles', '6.2137')]:
    got = mathtalk.answer(q)
    ok('convert: ' + q, bool(got) and got[0] == 'convert' and frag in got[1])

for q in ['у меня 3 яблока плюс 2 груши', 'я купил 17 штук, сколько ты купила', 'сколько тебе лет', 'what is love', 'расскажи про 2 и 3', 'сколько будет 2026-11-05', 'I have 3 apples times 2 maybe',
          'переведи это на английский', 'сколько будет 100 долларов в рублях', 'оценка 5-6 баллов', '오늘 날씨 어때', '今日は何をしたの', '', 'my number is 555-1234']:
    ok('silent: ' + q, mathtalk.answer(q) is None and mathtalk.hint(q) == '')
h = mathtalk.hint('сколько будет 17 умножить на 23')
ok('the note carries the number and forbids recounting', '391' in h and 'не пересчитывай' in h)
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.py'), encoding='utf-8').read()
ok('wired into the chat route', 'mathtalk.hint(text)' in src)
