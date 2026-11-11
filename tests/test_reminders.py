"""A reminder he asks for: read from the message in ru, en, ko, ja, kept, and said by her when its time comes (reminders.py, character.add_reminder)."""
import os
import sys
import time
import tempfile
import pathlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import character, reminders, convo
character.MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'   # never her real memory
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

now = 1_800_000_000.0
CASES = [('напомни мне через 10 минут про чай', 600, 'чай'), ('напомни через 2 часа позвонить маме', 7200, 'позвонить маме'), ('напомни через полчаса', 1800, ''),
         ('remind me in 15 minutes to drink tea', 900, 'drink tea'), ('remind me in an hour to call mom', 3600, 'call mom'),
         ('10분 뒤에 알려줘 차 마시기', 600, ''), ('2시간 후에 알람 맞춰줘', 7200, ''),
         ('10分後にリマインドして', 600, ''), ('2時間後に起こして', 7200, '')]
for text, secs, about in CASES:
    got = reminders.parse(text, now)
    ok('parse: ' + text, got is not None and abs(got[0] - now - secs) < 1 and (not about or about in got[1]))
local = time.localtime(now)
got = reminders.parse('напомни в %02d:%02d про встречу' % ((local.tm_hour + 2) % 24, local.tm_min), now)
ok('clock time: within a day, subject kept', got is not None and 3600 < got[0] - now <= 86400 and 'встречу' in got[1])
for text in ['напомни мне потом про чай', 'remind me later', 'расскажи про чай', 'через 10 минут будет дождь', 'in 10 minutes it rains', 'напомни через 0 минут', 'remind me in 99999 hours']:
    ok('no reminder: ' + text, reminders.parse(text, now) is None)
ok('without a time she is told not to promise', 'Не обещай' in str(convo.hints([], 'напомни мне потом про чай')))
ok('with a time that hint is not shown', 'Не обещай' not in str(convo.hints([], 'напомни мне через 10 минут про чай')))

character.MEMORY['reminders'] = []
ok('added', character.add_reminder(now + 60, 'чай') and character.add_reminder(now + 30, 'звонок'))
ok('kept in time order', [e['text'] for e in character.MEMORY['reminders']] == ['звонок', 'чай'])
ok('not due yet', character.reminders_due(now) == [])
ok('one is due', [e['text'] for e in character.reminders_due(now + 45)] == ['звонок'])
ok('taken once', [e['text'] for e in character.take_reminders(now + 45)] == ['звонок'] and character.take_reminders(now + 45) == [])
ok('the other waits', [e['text'] for e in character.MEMORY['reminders']] == ['чай'])
for i in range(20):
    character.add_reminder(now + 1000 + i, 'x%d' % i)
ok('the list is limited', len(character.MEMORY['reminders']) == character.REMINDER_LIMIT)
character.save_memory(); character.MEMORY['reminders'] = []; character.load_memory()
ok('reminders survive a restart', len(character.MEMORY['reminders']) == character.REMINDER_LIMIT)

# over HTTP: the page asks whether something is due; and the page polls for it
import json, threading, urllib.request
import app
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8805), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d):
    rq = urllib.request.Request('http://127.0.0.1:8805' + path, json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    with urllib.request.urlopen(rq) as x: return x.status, json.loads(x.read())
character.MEMORY['reminders'] = []
ok('http: nothing due', post('/reminder/due', {}) == (200, {'due': False}))
character.add_reminder(time.time() - 1, 'чай')
ok('http: something is due', post('/reminder/due', {}) == (200, {'due': True}))
js = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web', 'app.js'), encoding='utf-8').read()
ok('page: polls and speaks first, never on the stream', "api('/reminder/due'" in js and "converse('', 'remind')" in js and "'return', 'remind']" in js)


# ---- clock words and days, in all four languages: "в 6 вечера", "at 6pm", "오후 6시", "午後6時", "завтра в 9" ----
base = time.mktime((2026, 11, 5, 14, 0, 0, 0, 0, -1))
def at(day, h, m=0):
    return time.mktime((2026, 11, 5 + day, h, m, 0, 0, 0, -1))
CLOCKS = [
    ('напомни в 6 вечера про ужин', at(0, 18), 'ужин'), ('напомни в 9 утра позвонить', at(1, 9), 'позвонить'),
    ('напомни завтра в 9 утра про врача', at(1, 9), 'врача'), ('напомни в 7 часов вечера выключить плиту', at(0, 19), 'плиту'),
    ('напомни послезавтра в 10:30 про встречу', at(2, 10, 30), 'встречу'), ('напомни в 11 ночи лечь спать', at(0, 23), 'лечь'),
    ('remind me at 6pm to call mom', at(0, 18), 'call mom'), ('remind me at 6:30 pm about dinner', at(0, 18, 30), 'dinner'),
    ('remind me tomorrow at 9am to send the report', at(1, 9), 'report'), ('remind me at 8 to take pills', at(1, 8), 'pills'),
    ('오후 6시에 알려줘', at(0, 18), ''), ('내일 아침 9시에 알려줘 병원', at(1, 9), '병원'), ('저녁 7시 반에 알람 맞춰줘', at(0, 19, 30), ''),
    ('午後6時にリマインドして', at(0, 18), ''), ('明日の朝9時に教えて', at(1, 9), ''), ('夜10時半にアラーム', at(0, 22, 30), ''),
]
for text, want, about in CLOCKS:
    got = reminders.parse(text, base)
    ok('clock: ' + text, got is not None and abs(got[0] - want) < 1 and (not about or about in got[1]))
# the subject loses the time words
ok('subject keeps only the matter', reminders.parse('напомни завтра в 9 утра про врача', base)[1] == 'врача')
# "1 hour 30 minutes", "an hour and a half"
for text, secs in [('напомни через 1 час 30 минут про чай', 5400), ('напомни через 2 часа и 15 минут', 8100), ('remind me in 1 hour 20 minutes', 4800),
                   ('remind me in 1 hour and a half', 5400), ('1시간 30분 뒤에 알려줘', 5400), ('1時間30分後にリマインドして', 5400)]:
    got = reminders.parse(text, now)
    ok('compound: ' + text, got is not None and abs(got[0] - now - secs) < 1)
# not a reminder / not understood: she must not promise
for text in ['напомни завтра про чай', 'remind me tomorrow', 'напомни в 25 вечера', 'remind me at 5% of the time', 'расскажи про 6 вечера',
             'what happens at 6pm in Seoul', '내일 날씨 알려줘', '明日の天気を教えて', 'напомни через неделю']:
    ok('no reminder: ' + text, reminders.parse(text, base) is None)
ok('a day without a clock time gets the honest no', 'Не обещай' in str(convo.hints([], 'напомни завтра про чай')))
ok('a clock time in Korean gets no honest no', 'Не обещай' not in str(convo.hints([], '오후 6시에 알려줘')))

# the subject is what is left after the time and the asking words are gone, also in Korean and Japanese
for text, about in [('오후 6시에 알려줘 차 마시기', '차 마시기'), ('내일 아침 9시에 알려줘 병원', '병원'), ('午後6時に牛乳を買うことをリマインドして', '牛乳を買うこと'),
                    ('10分後にお茶を飲むように教えて', 'お茶を飲むように'), ('10분 뒤에 차 마시라고 알려줘', '차 마시라고')]:
    got = reminders.parse(text, base)
    ok('subject: ' + text, got is not None and got[1].startswith(about) and '알려' not in got[1] and '教えて' not in got[1])


# ---- seeing and cancelling the reminders she keeps, in four languages ----
for text in ['какие у меня напоминания', 'покажи мои напоминания', 'what reminders do I have', 'show my reminders', '알림 뭐 있어', 'リマインダーを見せて']:
    ok('list asked: ' + text, reminders.manage_kind(text) == 'list')
for text in ['отмени напоминание про чай', 'cancel the reminder about tea', '차 알림 취소해줘', 'お茶のリマインダーを消して', 'отмени все напоминания', 'cancel all my reminders']:
    ok('cancel asked: ' + text, reminders.manage_kind(text) == 'cancel')
for text in ['какая погода', 'напомни через 10 минут про чай', 'remind me in 10 minutes', 'расскажи про напоминания в телефоне', 'я не люблю напоминания', '今日は何をしたの', '오늘 날씨 어때']:
    ok('not about managing: ' + text, reminders.manage_kind(text) == '')
mine = [{'due': base + 600, 'text': 'чай'}, {'due': base + 7200, 'text': 'позвонить врачу'}, {'due': base + 90000, 'text': 'tea party'}]
hint = reminders.manage('какие у меня напоминания', mine)
ok('list names all of them and changes nothing', 'чай' in hint and 'врачу' in hint and 'tea party' in hint and len(mine) == 3)
hint = reminders.manage('отмени напоминание про чай', mine)
ok('one is cancelled by its subject', [e['text'] for e in mine] == ['позвонить врачу', 'tea party'] and 'убрала' in hint)
hint = reminders.manage('cancel the reminder about tea', mine)
ok('English cancel by subject', [e['text'] for e in mine] == ['позвонить врачу'])
hint = reminders.manage('отмени напоминание про зубы', mine)
ok('an unknown subject: nothing is removed, she asks which', len(mine) == 1 and 'не поняла' in hint)
hint = reminders.manage('отмени напоминание', mine)
ok('a single reminder can be cancelled without naming it', mine == [] and 'убрала' in hint)
ok('nothing to cancel is said honestly', 'их нет' in reminders.manage('отмени напоминание', mine))
mine = [{'due': base + 600, 'text': 'a'}, {'due': base + 700, 'text': 'b'}]
reminders.manage('отмени напоминание', mine)
ok('two reminders without a name: nothing is guessed', len(mine) == 2)
reminders.manage('отмени все напоминания', mine)
ok('"all" removes all', mine == [])
ok('the honest-no hint is not shown for managing', 'Не обещай' not in str(convo.hints([], 'отмени напоминание про чай')))
