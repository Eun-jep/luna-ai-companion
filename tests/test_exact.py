import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.skills import exact

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print('PASS', name)
    else:
        failed += 1
        print('FAIL', name)


ok('sum', exact.calc('2+2*2') == '2+2*2 = 6')
ok('long integers are exact', exact.calc('2**64') == '2**64 = 18446744073709551616')
ok('caret is a power', exact.calc('3^4') == '3^4 = 81')
ok('percent of', exact.calc('15% от 2300') == '15% от 2300 = 345')
ok('decimal comma', exact.calc('1,5*4') == '1,5*4 = 6')
ok('times sign between digits', exact.calc('12 x 12') == '12 x 12 = 144')
ok('functions keep their letters', exact.calc('max(3, 9)') == 'max(3, 9) = 9' and exact.calc('exp(0)') == 'exp(0) = 1')
ok('sqrt', exact.calc('sqrt(2)').endswith('1.41421356237'))
ok('float noise is trimmed', exact.calc('0.1+0.2') == '0.1+0.2 = 0.3')
ok('division by zero is nothing', exact.calc('1/0') == '')
ok('no names or attributes', exact.calc('__import__("os")') == '' and exact.calc('(1).__class__') == '' and exact.calc('open("x")') == '')
ok('no strings or lists', exact.calc('"a"*5') == '' and exact.calc('[1]*3') == '')
ok('huge power refused', exact.calc('9**9**9') == '' and exact.calc('10**5000') == '')
ok('long input refused', exact.calc('1+' * 150 + '1') == '')
ok('empty', exact.calc('') == '' and exact.calc(None) == '')
ok('days between', exact.calc('2026-01-01 - 2026-11-03') == '306 дн. между 2026-01-01 и 2026-11-03')
ok('date plus days', exact.calc('2026-11-03 + 90') == '2026-11-03 + 90 дн. = 2027-02-01 (пн)')
ok('bad date', exact.calc('2026-13-45 + 3') == '')
ok('factorial', exact.calc('fact(10)') == 'fact(10) = 3628800' and exact.calc('fact(100000)') == '')
print('test_exact.py pass=%d fail=%d' % (passed, failed))
sys.exit(1 if failed else 0)


# ---- units: the program converts by factor, in four languages; money and mixed kinds are not converted ----
for text, want in [('10 km in miles', '10 km = 6.21371192 mi'), ('5 фунтов в кг', '5 lb = 2.26796185 kg'), ('100°F в °C', '100°F = 37.777778°C'),
                   ('5キロをマイルに', '5 km = 3.10685596 mi'), ('10 마일을 킬로미터로', '10 mi = 16.09344 km'), ('1시간을 분으로', '1 h = 60 min'),
                   ('3 hours to minutes', '3 h = 180 min'), ('2 гб в мб', '2 gb = 2048 mb'), ('0 C to F', '0°C = 32°F'), ('5 km/h to mph', '5 km/h = 3.10685596 mph'),
                   ('300 K to C', '300 K = 26.85°C'), ('1,5 кг в г', '1.5 kg = 1500 g')]:
    ok('convert: ' + text, exact.calc(text) == want)
for text in ['1 kg to m', '100 USD to EUR', '5 евро в рубли', '-300 C to K', '10 km in km', 'сколько будет 5 в степени 2', '2+2*3']:
    ok('not a conversion: ' + text, 'km' not in exact.convert(text) and exact.convert(text) == '')
ok('plain sums still work next to units', exact.calc('2+2*3') == '2+2*3 = 8' and exact.calc('15% от 2300') == '15% от 2300 = 345')


# ---- dates: "today" is known to the program, and one date alone gives its weekday ----
import datetime as _dt
_today = _dt.date.today()
_far = _today + _dt.timedelta(days=100)
ok('days until a date, from today', exact.calc('%s - today' % _far.isoformat()).startswith('100 дн.'))
ok('today in Russian, Korean and Japanese', all(exact.calc('%s - %s' % (_far.isoformat(), w)).startswith('100 дн.') for w in ('сегодня', '오늘', '今日')))
ok('today plus days', exact.calc('today + 10').startswith(_today.isoformat() + ' + 10 дн. = ' + (_today + _dt.timedelta(days=10)).isoformat()))
ok('a single date gives its weekday', exact.calc('2027-03-01') == '2027-03-01: понедельник' and exact.calc('2026-11-05') == '2026-11-05: четверг')
ok('two dates still count days between', exact.calc('2026-01-01 - 2026-11-03').startswith('306 дн.'))
ok('words with today inside are not touched', exact.calc('sqrt(16) * 3') == 'sqrt(16) * 3 = 12')
