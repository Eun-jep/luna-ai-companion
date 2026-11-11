"""Habits (habits.py): start, mark, show, drop in ru, en, ko, ja; streak counting; honest answers; never touches his real habits.json."""
import os
import sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import habits
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

ok('sandboxed under tests', 'luna-data-' in str(habits.FILE))

for text, kind, name in [('заведи привычку зарядка', 'start', 'зарядка'), ('добавь привычку пить воду', 'start', 'пить воду'),
                         ('track a habit: reading', 'start', 'reading'), ('start tracking my running habit', 'start', 'running'),
                         ('운동 습관 추가해줘', 'start', '운동'), ('習慣を追加 読書', 'start', '読書'), ('読書を習慣にして', 'start', '読書'),
                         ('отметь зарядку', 'mark', 'зарядку'), ('отметь зарядку сегодня', 'mark', 'зарядку'), ('mark reading as done', 'mark', 'reading'),
                         ('log my reading habit', 'mark', 'reading'), ('운동 체크해줘', 'mark', '운동'), ('運動を記録して', 'mark', '運動'),
                         ('как мои привычки', 'show', ''), ('show my habits', 'show', ''), ('습관 현황 알려줘', 'show', ''), ('習慣の状況を教えて', 'show', ''),
                         ('удали привычку зарядка', 'drop', 'зарядка'), ('delete the reading habit', 'drop', 'reading'), ('운동 습관 삭제해줘', 'drop', '운동'),
                         ('読書の習慣を削除', 'drop', '読書')]:
    got = habits.parse(text)
    ok('parsed: ' + text, bool(got) and got[0] == kind and (not name or got[1] == name))
for text in ['у меня плохая привычка грызть ногти, как избавиться', 'какая погода', 'I have a habit of walking at night', 'привычка вторая натура', '', '오늘 날씨 어때', '今日は何をしたの',
             'как ты относишься к привычкам']:
    ok('not a habit request: ' + text, habits.parse(text) is None and habits.handle(text) == '')
ok('"отметь" about something else is silent when it is not a habit', habits.handle('отметь это место на карте', today=date(2026, 1, 1)) == '')

# streak arithmetic
t = date(2026, 3, 10)
days = [(t - timedelta(days=i)).isoformat() for i in range(0, 5)]
ok('streak of five counted from today', habits.streaks(days, t) == (5, 5, 5))
ok('streak stays alive until the day ends', habits.streaks([(t - timedelta(days=i)).isoformat() for i in range(1, 4)], t) == (3, 3, 3))
ok('a gap breaks it, the best one is kept', habits.streaks([(t - timedelta(days=i)).isoformat() for i in (3, 4, 5, 6, 7, 1)], t)[:2] == (1, 5))
ok('two days missed means zero now', habits.streaks([(t - timedelta(days=i)).isoformat() for i in (2, 3)], t)[0] == 0)
ok('empty', habits.streaks([], t) == (0, 0, 0))

# the whole flow on a sandboxed file
h = habits.handle('заведи привычку зарядка', today=t)
ok('start answers and stores', 'завела' in h and 'зарядка' in h and 'зарядка' in habits.load())
ok('same habit twice is not duplicated', 'уже есть' in habits.handle('заведи привычку зарядка', today=t) and len(habits.load()) == 1)
h = habits.handle('отметь зарядку', today=t)
ok('first mark gives a one-day streak', 'серия 1' in h and 'всего 1' in h)
ok('the same day twice does not count', 'уже была отмечена' in habits.handle('отметь зарядку', today=t) and len(habits.load()['зарядка']['days']) == 1)
habits.handle('отметь зарядку вчера', today=t)
ok('yesterday can be marked after the fact', (t - timedelta(days=1)).isoformat() in habits.load()['зарядка']['days'])
h = habits.handle('mark exercise as done', today=t)
ok('unknown habit with no habit word stays silent', h == '')
ok('unknown habit with the word is an honest no', 'нет' in habits.handle('log my yoga habit', today=t) and 'yoga' not in habits.load())
ok('inflected name matches (зарядку ~ зарядка)', 'серия 3' in habits.handle('отметь зарядку', today=t + timedelta(days=1)))
h = habits.handle('как мои привычки', today=t + timedelta(days=1))
ok('show carries the real numbers and the no-reproach instruction', 'зарядка: серия' in h and 'не упрекай' in h)
ok('empty list says there are none', (lambda: (habits.FILE.unlink(), 'нет' in habits.handle('как мои привычки', today=t))[1])())
habits.handle('заведи привычку чтение', today=t)
ok('drop removes one', 'убрала' in habits.handle('удали привычку чтение', today=t) and 'чтение' not in habits.load())
ok('drop of unknown is an honest no', 'не нашла' in habits.handle('удали привычку полёты', today=t))
for i in range(habits.MAX_HABITS + 2):
    habits.handle('заведи привычку дело%s' % chr(97 + i), today=t)
ok('habits are capped', len(habits.load()) <= habits.MAX_HABITS)
habits.handle('заведи привычку сон', today=t)
for k in range(2, 0, -1):
    habits.handle('отметь сон', today=t - timedelta(days=k))
h = habits.handle('отметь сон', today=t)
ok('third day in a row is a milestone', 'серия 3' in h and 'круглая серия' in h)
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.py'), encoding='utf-8').read()
ok('wired into the chat route', 'habits.handle(text)' in src)
