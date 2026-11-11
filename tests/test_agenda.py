"""'What is on today' (agenda.py): asked in ru, en, ko, ja; the plan is built only from what the program really keeps, nothing is invented."""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.skills import agenda
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

for text in ['что у меня на сегодня', 'какие планы на завтра', 'мои дела на сегодня', "what's on today", 'what do I have tomorrow', "what's on my schedule",
             '오늘 일정 뭐야', '내일 할 일 알려줘', '今日の予定は', '明日のやることを教えて']:
    ok('asked: ' + text, agenda.asks(text))
for text in ['какая погода', 'расскажи про планы на жизнь', 'what is the weather', "it's a plan", '오늘 날씨 어때', '今日は何をしたの', '', 'добавь молоко в список покупок']:
    ok('not asked: ' + text, not agenda.asks(text) and agenda.hint(text, [], [], []) == '')

now = time.mktime((2026, 11, 5, 10, 0, 0, 0, 0, -1))
at = lambda day, h, m=0: time.mktime((2026, 11, 5 + day, h, m, 0, 0, 0, -1))
reminders = [{'due': at(0, 18), 'text': 'ужин'}, {'due': at(1, 9), 'text': 'врач'}, {'due': at(0, 12, 30), 'text': ''}]
moments = [{'due': at(0, 0), 'text': 'экзамен', 'kind': 'event'}, {'due': at(3, 0), 'text': 'поездка', 'kind': 'event'}, {'due': 0, 'text': 'бросить курить', 'kind': 'promise'}]
todo = ['позвонить маме', 'оплатить интернет']
h = agenda.hint('что у меня на сегодня', reminders, moments, todo, now)
ok('today: reminders in time order', h.index('12:30') < h.index('18:00 ужин'))
ok('today: dated moment and the to-do list', 'экзамен' in h and 'позвонить маме' in h and 'оплатить интернет' in h)
ok('today: tomorrow and later things are not mixed in', 'врач' not in h and 'поездка' not in h and 'бросить курить' not in h)
h = agenda.hint("what's on tomorrow", reminders, moments, todo, now)
ok('tomorrow: only tomorrow\'s reminder', '09:00 врач' in h and 'ужин' not in h and 'экзамен' not in h)
h = agenda.hint('오늘 일정 뭐야', [], [], [], now)
ok('nothing kept: she is told to say so, not to invent', 'ничего не записано' in h and 'не выдумывай' in h)
h = agenda.hint('今日の予定は', [], [], ['x%d' % i for i in range(14)], now)
ok('a long to-do list is cut with a count', 'и ещё 4' in h)
src = ''.join(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), *f), encoding='utf-8').read() for f in (('app.py',), ('luna', 'server', 'chat.py'), ('luna', 'server', 'hands.py'), ('luna', 'core', 'prompts.py')))
ok('wired into the chat route', 'agenda.hint(text' in src)
h = agenda.hint('что у меня на сегодня', [], [], [], now, habits_left=['зарядка', 'чтение'])
ok('today: habits not yet marked are listed', 'зарядка' in h and 'чтение' in h and 'не отмечены' in h)
h = agenda.hint('какие планы на завтра', [], [], [], now, habits_left=['зарядка'])
ok('tomorrow: habits are not listed', 'зарядка' not in h)
