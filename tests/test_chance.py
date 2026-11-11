"""Coin, dice, random number and "pick one" (chance.py): asked in ru, en, ko, ja; the program throws, she only announces the result."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chance
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

for text, want in [('подбрось монетку', ('coin',)), ('heads or tails?', ('coin',)), ('flip a coin', ('coin',)), ('동전 던져줘', ('coin',)), ('コイン投げて', ('coin',)),
                   ('брось кубик', ('dice', 1, 6)), ('кинь 2d6', ('dice', 2, 6)), ('roll a d20', ('dice', 1, 20)), ('roll 3d6', ('dice', 3, 6)),
                   ('주사위 굴려줘', ('dice', 1, 6)), ('サイコロ振って', ('dice', 1, 6)),
                   ('случайное число от 1 до 100', ('range', 1, 100)), ('random number between 1 and 10', ('range', 1, 10)),
                   ('1부터 100까지 랜덤 숫자', ('range', 1, 100)), ('1から10でランダム', ('range', 1, 10)), ('случайное число от 10 до 1', ('range', 1, 10)),
                   ('выбери: пицца или суши', ('pick', ['пицца', 'суши'])), ('choose between tea or coffee', ('pick', ['tea', 'coffee'])),
                   ('pick one: red, green, blue', ('pick', ['red', 'green', 'blue'])), ('차 아니면 커피 중에 골라줘', ('pick', ['차', '커피'])),
                   ('紅茶かコーヒーか選んで', ('pick', ['紅茶', 'コーヒー']))]:
    ok('asked: ' + text, chance.parse(text) == want)
for text in ['какая погода', 'у меня монетка в кармане', 'I like dice games', 'чай или кофе?', 'what is 2d6 in math', '오늘 날씨 어때', '今日は何をしたの', '', 'расскажи про кубики льда']:
    ok('not a throw: ' + text, chance.parse(text) is None and chance.hint(text) == '')
ok('dice are capped', chance.parse('roll 99d9999') == ('dice', chance.MAX_DICE, chance.MAX_SIDES))

# the throw itself: every result is inside the range, and both sides of a coin come up
coins = {chance.throw(('coin',)) for _ in range(60)}
ok('a coin has two sides', coins == {'монета: орёл', 'монета: решка'})
ok('a die stays between 1 and 6', all(1 <= int(chance.throw(('dice', 1, 6)).split(': ')[1]) <= 6 for _ in range(100)))
ok('several dice give a sum', 'сумма' in chance.throw(('dice', 3, 6)))
ok('a number stays in its range', all(-5 <= int(chance.throw(('range', -5, 5)).split(': ')[-1]) <= 5 for _ in range(100)))
picked = {chance.throw(('pick', ['a', 'b', 'c'])).split(': ')[-1] for _ in range(100)}
ok('pick chooses only from the options and can reach each', picked == {'a', 'b', 'c'})
chance.RNG = type('R', (), {'choice': lambda s, seq: seq[0], 'randint': lambda s, a, b: b})()
h = chance.hint('выбери: пицца или суши')
ok('the hint carries the real result and forbids changing it', 'пицца' in h and 'не меняй' in h)
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.py'), encoding='utf-8').read()
ok('wired into the chat route', 'chance.hint(text)' in src)
