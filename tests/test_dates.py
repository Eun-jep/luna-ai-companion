"""Calendar counting (dates.py): asked in ru, en, ko, ja; every number is checked against datetime done separately; silent when no readable date is named."""
import os
import sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.skills import dates
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

T = date(2026, 11, 6)
h = lambda q, today=T: dates.handle(q, today)
to_ny = (date(2027, 1, 1) - T).days
to_xmas = (date(2026, 12, 25) - T).days

for q in ['сколько дней до 1 января', 'сколько дней до нового года', 'how many days until New Year', 'how many days until 2027-01-01', '새해까지 며칠', '来年の1月1日まであと何日', '新年まであと何日', 'сколько осталось до 1 января 2027']:
    ok('until the new year, %d days: %s' % (to_ny, q), ('%d дн' % to_ny) in h(q))
for q in ['how many days until Christmas', 'сколько дней до католического Рождества', '크리스마스까지 며칠', 'クリスマスまであと何日', 'сколько дней до 25 декабря', 'days until December 25']:
    ok('until Christmas, %d days: %s' % (to_xmas, q), ('%d дн' % to_xmas) in h(q))
ok('the Russian Christmas is the Orthodox one and says so', '7 января 2027' in h('сколько дней до рождества') and 'православное' in h('сколько дней до рождества'))
ok('a date that already passed this year means next year', '5 января 2027' in h('сколько дней до 5 января'))
ok('today is said to be today', 'это сегодня' in h('сколько дней до 6 ноября'))
ok('Feb 29 waits for the leap year', '29 февраля 2028' in h('how many days until February 29'))

ok('between two dates', '35 дн' in h('сколько дней между 1 марта и 5 апреля') and '35 дн' in h('how many days between March 1 and April 5') and '35 дн' in h('3월 1일부터 4월 5일까지 며칠') and '35 дн' in h('3月1日から4月5日まで何日'))
ok('between in reverse order is the same', '35 дн' in h('between April 5 and March 1'))
ok('between with a year', '%d дн' % (date(2027, 1, 1) - date(2026, 1, 1)).days in h('сколько дней между 2026-01-01 и 2027-01-01'))

want = (T + timedelta(days=100))
ok('in 100 days', '%d %s %d' % (want.day, dates._MONTHS[want.month - 1], want.year) in h('через 100 дней какая дата') and '%d %s %d' % (want.day, dates._MONTHS[want.month - 1], want.year) in h('what date is 100 days from now'))
ok('in 100 days: ko and ja', all('14 февраля 2027' in h(q) for q in ['100일 후 날짜 알려줘', '100日後は何日', '100 days from now what date']))
ok('weeks and months', '4 декабря 2026' in h('какая дата через 4 недели') and '6 февраля 2027' in h('какая дата через 3 месяца'))
ok('ago', '1 ноября 2026' in h('какая дата была 5 дней назад') and '30 октября 2026' in h('what date was 7 days ago') or '30 октября 2026' in h('what date is 7 days ago'))
ok('month end is clamped (Jan 31 + 1 month)', '28 февраля 2027' in h('какая дата через 1 месяц', date(2027, 1, 28)) and '28 февраля 2027' in h('какая дата через 1 месяц', date(2027, 1, 31)))

ok('weekday of a date', 'пятница' in h('what day of the week is March 5') and 'пятница' in h('какой день недели 5 марта 2027') and 'вторник' in h('2026-12-01은 무슨 요일'))
ok('weekday in ja', 'вторник' in h('2026年12月1日は何曜日'))
ok('weekday of tomorrow', 'суббота' in h('what day of the week is tomorrow'))

ok('age in years, months, days', '36 лет 5 месяцев 25 дней' in h('сколько мне лет, если я родился 12.05.1990'))
ok('age: the next birthday is counted', 'через 187 дней' in h('сколько мне лет, если я родился 12.05.1990'))
ok('age in en, ko, ja', all('31 год' in h(q) for q in ['how old am I if I was born on 1995-03-20', '1995-03-20에 태어났는데 몇 살이야', '1995-03-20に生まれたら何歳']))
ok('since a date', '66 дн' in h('сколько дней прошло с 1 сентября') and '66 дн' in h('how many days since September 1') and '66 дн' in h('9월 1일부터 며칠 지났어') and '66 дн' in h('9月1日から何日経った'))
ok('since: a year is used when given', '%d дн' % (T - date(2020, 2, 29)).days in h('сколько дней прошло с 29 февраля 2020'))

ok('a date that does not exist is an honest no', 'которой нет' in h('сколько дней до 31 апреля') and 'которой нет' in h('between 2026-02-30 and March 1'))
for q in ['сколько дней до отпуска', 'напомни через 3 дня купить хлеб', 'how long to boil an egg', 'remind me in 3 days', 'какая погода', 'сколько будет 2+2', 'расскажи про календарь',
          '오늘 날씨 어때', '今日は何をしたの', '', 'через час какая погода', 'я родился в Москве, сколько там людей']:
    ok('silent: ' + q, h(q) == '')
ok('weekday and today are in every answer', 'Сегодня 6 ноября 2026 (пятница)' in h('сколько дней до 1 января'))
ok('the note forbids recounting', 'не пересчитывай' in h('сколько дней до 1 января'))
src = ''.join(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), *f), encoding='utf-8').read() for f in (('app.py',), ('luna', 'server', 'chat.py'), ('luna', 'server', 'hands.py'), ('luna', 'core', 'prompts.py')))
ok('wired into the chat route', 'dates.handle(text)' in src)
