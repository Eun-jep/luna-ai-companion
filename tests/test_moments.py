"""Dates, promises, habits and care on her own initiative (character.py). Uses a fake model and a fake clock."""
import os
import sys, tempfile, pathlib, json, time as real_time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.core import character as C
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)


class Clock:
    """The real time module, but "now" and the hour can be moved."""
    def __init__(self):
        self.now = real_time.mktime((2026, 11, 2, 10, 0, 0, 0, 0, -1))
        self.hour = None

    def time(self):
        return self.now

    def localtime(self, t=None):
        lt = real_time.localtime(self.now if t is None else t)
        if t is None and self.hour is not None:
            lt = real_time.struct_time((lt.tm_year, lt.tm_mon, lt.tm_mday, self.hour) + tuple(lt)[4:])
        return lt

    def __getattr__(self, name):
        return getattr(real_time, name)


clock = Clock()
C.time = clock
tmp = pathlib.Path(tempfile.mkdtemp()); C.MEMORY_FILE = tmp / 'memory.json'
C.load_memory()
ok('fresh memory: no moments, nothing to care about, prompt block empty', C.MEMORY['moments'] == [] and C.moments_block() == '' and C.care_note() == '')

answer = {}
calls = []
def llm(messages):
    calls.append(messages)
    return json.dumps(answer)
C.llm = llm
answer.update(user=['Его зовут Вадим'], me=[], moments=[
    {'kind': 'date', 'text': 'Экзамен по математике', 'due': '2026-11-03'},
    {'kind': 'promise', 'text': 'Обещал сходить к врачу', 'due': ''},
    {'kind': 'habit', 'text': 'Часто сидит до утра', 'due': ''},
    {'kind': 'junk', 'text': 'не тот вид', 'due': ''},
    {'kind': 'date', 'text': '', 'due': ''},
    'строка вместо объекта',
    {'kind': 'date', 'text': 'Экзамен по математике', 'due': '2026-11-03'}])
C.update_memory([{'role': 'user', 'content': 'завтра экзамен, я обещал сходить к врачу'}])
texts = [m['text'] for m in C.MEMORY['moments']]
ok('moments are extracted; junk, empty and duplicates are skipped', texts == ['Экзамен по математике', 'Обещал сходить к врачу', 'Часто сидит до утра'])
ok('today and current moments are sent to the model', 'Сегодня: 2026-11-02' in calls[-1][1]['content'])
ok('dated moment gets a real day', abs(C.MEMORY['moments'][0]['due'] - real_time.mktime((2026, 11, 3, 0, 0, 0, 0, 0, -1))) < 5)
block = C.moments_block()
ok('prompt shows the date as "завтра", promise and habit', '[дата, завтра] Экзамен' in block and '[обещание] Обещал' in block and '[привычка]' in block)
ok('memory_block includes the moments', 'Экзамен по математике' in C.memory_block('привет'))

# survives a restart
saved = C.MEMORY_FILE.read_text(encoding='utf-8')
C.MEMORY['moments'] = []
C.load_memory()
ok('moments reload from the file', len(C.MEMORY['moments']) == 3)

# care: the date comes first, once, then not again for 12 hours
n1 = C.care_note()
ok('care about tomorrow\'s exam', 'Экзамен по математике' in n1 and 'завтра' in n1)
ok('same moment is not repeated right away', 'Экзамен' not in C.care_note())
clock.now += 13 * 3600
ok('...but after 12 hours it can be mentioned again (n<3)', 'Экзамен' in C.care_note())
clock.now += 13 * 3600
C.care_note()
clock.now += 13 * 3600
ok('...and never more than CARE_MAX times: no nagging', 'Экзамен' not in C.care_note())

# a promise with no date is asked about once, a day later; habits are never asked about
ok('after the date is used up, the undated promise gets its turn (once)', C.MEMORY['moments'][1]['n'] == 1)
C.MEMORY['moments'][1].update(t=clock.now - 2 * 86400, n=0, cared=0)
note = C.care_note()
ok('undated promise: one gentle question', 'врач' in note and 'без давления' in note)
ok('...asked only once', C.care_note() == '')
ok('habit alone never triggers a reminder', all(m['kind'] != 'habit' or m['n'] == 0 for m in C.MEMORY['moments']))

# a past date is dropped after three days
C.MEMORY['moments'][0]['due'] = clock.now - 4 * 86400
C.tidy_moments()
ok('long-past dated moment is forgotten', all(m['text'] != 'Экзамен по математике' for m in C.MEMORY['moments']))

# keeping history across model updates: same text keeps its counter
answer['moments'] = [{'kind': 'promise', 'text': 'Обещал сходить к врачу', 'due': ''}]
C.update_memory([{'role': 'user', 'content': 'x'}])
ok('an updated list keeps the counter of moments that stayed', len(C.MEMORY['moments']) == 1 and C.MEMORY['moments'][0]['n'] == 1)
del answer['moments']
C.update_memory([{'role': 'user', 'content': 'x'}])
ok('no "moments" key from the model leaves the list alone', len(C.MEMORY['moments']) == 1)
answer['moments'] = []
C.update_memory([{'role': 'user', 'content': 'x'}])
ok('an empty list from the model clears finished things', C.MEMORY['moments'] == [])

# late night -> care the next morning
C.MEMORY['late'] = C.MEMORY['late_cared'] = 0
clock.hour = 3
C.note_activity()
ok('a message at 3 a.m. is remembered', C.MEMORY['late'] == clock.now)
clock.hour = 2; clock.now += 3600
ok('still night: no care yet', C.care_note() == '')
clock.hour = 9; clock.now += 6 * 3600
late = C.care_note()
ok('next morning: a warm question about sleep', 'допоздна' in late and 'без нравоучений' in late)
ok('...once only', C.care_note() == '')
clock.hour = 3; C.note_activity(); clock.hour = 9; clock.now += 20 * 3600
ok('an old late night (over 16 h) is not brought up', C.care_note() == '')
clock.hour = 14; C.MEMORY['late'] = clock.now - 3600; C.MEMORY['late_cared'] = 0
clock.hour = 20
ok('not in the evening either', C.care_note() == '')

# damaged moments in the file
for bad in ({'moments': 'x'}, {'moments': [1, {'kind': 'date'}, {'kind': 'date', 'text': 'ok', 'due': 'bad', 'n': 'x'}], 'late': 'x'}):
    C.MEMORY['moments'] = []
    C.MEMORY_FILE.write_text(json.dumps(bad), encoding='utf-8')
    try:
        C.load_memory(); r = True
    except Exception:
        r = False
    ok('damaged moments in the file do not crash loading', r)
ok('only the valid moment survived', [m['text'] for m in C.MEMORY['moments']] == ['ok'] and C.MEMORY['moments'][0]['due'] == 0.0)
ok('bad dates parse to 0', C.parse_due('2026-13-45') == 0.0 and C.parse_due('abc') == 0.0 and C.parse_due('') == 0.0)


# ---- goodnight at night -> a warm good morning with "how did you sleep" next day, once ----
C.MEMORY['late'] = C.MEMORY['late_cared'] = 0; C.MEMORY['bed'] = C.MEMORY['bed_cared'] = 0; C.MEMORY['moments'] = []
clock.hour = 14; C.note_goodnight()
ok('a goodnight in the afternoon is not a bedtime', C.MEMORY['bed'] == 0)
clock.hour = 23; C.note_goodnight()
ok('a goodnight at 23:00 is remembered', C.MEMORY['bed'] == clock.now)
clock.hour = 23; clock.now += 3600
ok('the same night: nothing yet', C.care_note() == '')
clock.hour = 8; clock.now += 8 * 3600
morning = C.care_note()
ok('next morning: good morning and how did you sleep', 'спокойной ночи' in morning and 'спалось' in morning)
ok('...once only', C.care_note() == '' or 'спокойной ночи' not in C.care_note())
C.MEMORY['bed'] = clock.now - 30 * 3600; C.MEMORY['bed_cared'] = 0
ok('a goodnight from a day and a half ago is not brought up', 'спокойной ночи' not in C.care_note())
C.MEMORY['bed'] = clock.now - 9 * 3600; C.MEMORY['bed_cared'] = 0; clock.hour = 15
ok('not in the afternoon either', 'спокойной ночи' not in C.care_note())


# ---- something heavy was left unsaid: next time she asks how he is, once; cheering up in the same talk cancels it ----
C.MEMORY['late'] = C.MEMORY['late_cared'] = 0; C.MEMORY['bed'] = C.MEMORY['bed_cared'] = 0; C.MEMORY['moments'] = []
C.MEMORY['worry'] = {'t': 0, 'tone': ''}
clock.hour = 21; clock.now = real_time.mktime((2026, 11, 3, 21, 0, 0, 0, 0, -1))
C.sense('мне так грустно сегодня')
ok('sadness is kept as something left with her', C.MEMORY['worry']['tone'] == 'sad' and C.MEMORY['worry']['t'] == clock.now)
C.sense('какая погода')
ok('a neutral message does not erase it', C.MEMORY['worry']['tone'] == 'sad')
clock.now += 3600; clock.hour = 22
ok('right after (an hour): she does not ask yet', 'грустно' not in C.care_note())
clock.now += 12 * 3600; clock.hour = 10
asked = C.care_note()
ok('next day: a soft question about how he is', 'грустно' in asked and 'без допроса' in asked)
ok('...once only', 'грустно' not in C.care_note())
clock.now = real_time.mktime((2026, 11, 4, 20, 0, 0, 0, 0, -1)); clock.hour = 20
C.sense('меня это бесит'); clock.now += 600; C.sense('ура, получилось!')
ok('cheering up in the same talk cancels the worry', C.MEMORY['worry']['t'] == 0)
C.sense('мне так грустно'); clock.now += 5 * 86400; clock.hour = 10
ok('a worry from days ago is not brought up', 'грустно' not in C.care_note() and 'зол' not in C.care_note())
C.sense('мне так грустно'); clock.now += 5 * 3600; clock.hour = 3
ok('not in the night', 'грустно' not in C.care_note())
for lang_text in ('너무 우울해', '寂しいよ'):
    C.MEMORY['worry'] = {'t': 0, 'tone': ''}; C.sense(lang_text)
    ok('worry is kept for Korean and Japanese too: ' + lang_text, C.MEMORY['worry']['tone'] == 'sad')


# ---- being ill: kept like a worry, asked about next time (not a diagnosis), in four languages; cheering up cancels it ----
C.MEMORY['worry'] = {'t': 0, 'tone': ''}
clock.hour = 21; clock.now = real_time.mktime((2026, 11, 3, 21, 0, 0, 0, 0, -1))
C.sense('у меня сильно болит голова')
ok('illness is kept as something left with her', C.MEMORY['worry']['tone'] == 'sick')
clock.now += 12 * 3600; clock.hour = 10
asked = C.care_note()
ok('next day she asks about his health', 'нездоровилось' in asked and 'без допроса' in asked)
ok('...once only', 'нездоровилось' not in C.care_note())
ok('the hint is not a diagnosis', 'не врач' in C.TONE_HINT['sick'])
for lang_text in ('i have a fever', '감기 걸렸어', '風邪ひいた', 'i feel sick'):
    C.MEMORY['worry'] = {'t': 0, 'tone': ''}; C.sense(lang_text)
    ok('illness is kept in every language: ' + lang_text, C.MEMORY['worry']['tone'] == 'sick')
for plain in ('температура на улице плюс пять', 'what a cold winter this is', '오늘 기분 좋아', '今日は天気がいい'):
    C.MEMORY['worry'] = {'t': 0, 'tone': ''}; C.sense(plain)
    ok('not illness: ' + plain, C.MEMORY['worry']['tone'] != 'sick')
