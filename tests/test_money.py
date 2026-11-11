"""Exchange rates on request (money.py): asked in ru, en, ko, ja; only with the Actions switch; the network is faked here, nothing leaves the computer."""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import money, netsearch
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

for text, want in [('100 долларов в вонах', (100.0, 'USD', 'KRW')), ('сколько будет 50 евро в долларах', (50.0, 'EUR', 'USD')), ('100 USD to KRW', (100.0, 'USD', 'KRW')),
                   ('how much is 50 euro in yen', (50.0, 'EUR', 'JPY')), ('100ドルは何円', (100.0, 'USD', 'JPY')), ('1000원은 몇 엔', (1000.0, 'KRW', 'JPY')),
                   ('10 € in $', (10.0, 'EUR', 'USD')), ('1 500 евро в юанях', (1500.0, 'EUR', 'CNY')), ('1,5 доллара в евро', (1.5, 'USD', 'EUR'))]:
    ok('asked: ' + text, money.parse(text) == want)
for text in ['какая погода', 'курс доллара', 'мне 100 лет', 'I have 100 dollars', '오늘 날씨 어때', '今日は何をしたの', '100 долларов', '', 'add 5 to 6', '10 kg to lb']:
    ok('not a conversion: ' + text, money.parse(text) is None and money.hint(text, True) == '')

calls = []
def fake(url, accept=''):
    calls.append(url)
    return 200, {}, json.dumps({'amount': 100.0, 'base': 'USD', 'date': '2026-11-04', 'rates': {'KRW': 138765.5}}).encode()
netsearch._get = fake
h = money.hint('100 долларов в вонах', True)
ok('with the switch on: the figure and the date of the rate', '138765.5 KRW' in h and '2026-11-04' in h and 'курсы меняются' in h)
ok('only codes and the amount are sent', calls and calls[0] == 'https://api.frankfurter.app/latest?amount=100&from=USD&to=KRW')
n = len(calls)
h = money.hint('100 долларов в вонах', False)
ok('switch off: no network, she says she can when it is on', len(calls) == n and 'Действия' in h and 'наугад' in h)
h = money.hint('100 рублей в долларах', True)
ok('rubles: honest refusal, no network', len(calls) == n and 'рубль не публикует' in h)
def down(url, accept=''):
    raise OSError('no network')
netsearch._get = down
h = money.hint('100 долларов в вонах', True)
ok('no network: she is told to say so', 'не удалось' in h and 'наугад' in h)
netsearch._get = lambda url, accept='': (500, {}, b'')
ok('a server error is also an honest no', 'не удалось' in money.hint('100 долларов в вонах', True))
netsearch._get = lambda url, accept='': (200, {}, b'not json')
ok('garbage from the service is an honest no', 'не удалось' in money.hint('100 USD to KRW', True))
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.py'), encoding='utf-8').read()
ok('wired into the chat route with the Actions switch', 'money.hint(text, AGENT)' in src)
