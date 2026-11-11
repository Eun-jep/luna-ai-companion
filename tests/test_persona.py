"""A person, not a servant: reading the creator's tone, hurt feelings, forgiveness, thanks (character.py + the prompt)."""
import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
from luna.core import character as C
from http.server import ThreadingHTTPServer
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
tmp = pathlib.Path(tempfile.mkdtemp()); C.MEMORY_FILE = tmp / 'memory.json'; app.load_memory()
M = C.MEMORY

def fresh():
    M['mood'] = {'v': 0.2, 'e': 0.5, 't': 0}; M['hurt'] = {'t': 0, 'text': ''}; M['sensed'] = {'t': 0, 'tone': ''}

cases = [('ты тупая, заткнись', 'rude'), ('Спасибо тебе огромное!', 'thanks'), ('thank you so much', 'thanks'), ('мне так грустно сегодня', 'sad'),
         ('я ужасно устал', 'tired'), ('меня это бесит', 'angry'), ('Ура, получилось!', 'happy'), ('прости меня', 'sorry'),
         ('ЭТО ПОЛНАЯ ЕРУНДА ВООБЩЕ', 'angry'), ('какая сегодня погода', ''), ('Я КОТ', ''), ('shut up', 'rude')]
for text, want in cases:
    fresh()
    got = C.sense(text)
    ok('tone of «%s» is %r' % (text, want), got == want)

fresh(); C.sense('какая погода')
ok('a neutral message changes nothing', M['mood']['v'] == 0.2 and M['hurt']['t'] == 0)
fresh(); before = C.mood_now()['v']; C.sense('ты тупая')
ok('rudeness hurts: mood drops and the offence is remembered', C.mood_now()['v'] < before - 0.2 and M['hurt']['t'] > 0 and 'тупая' in M['hurt']['text'])
ok('the hurt reaches the prompt right away', 'груб' in C.listen_block())
C.sense('ладно, проехали')
b = C.listen_block()
ok('afterwards she is still a bit hurt (without repeating the fresh-offence hint)', 'недавно обидели' in b and 'груб' not in b)
low = C.mood_now()['v']
C.sense('прости, я был неправ')
ok('an apology clears the offence and warms her', M['hurt']['t'] == 0 and C.mood_now()['v'] > low and 'прощения' in C.listen_block() and 'недавно обидели' not in C.listen_block())
fresh(); v0 = C.mood_now()['v']; C.sense('прости, что опоздал')
ok('an apology with nothing to forgive does not change her mood', C.mood_now()['v'] == v0 and M['hurt']['t'] == 0)
fresh(); C.sense('спасибо, ты лучшая'); ok('thanks lifts the mood and she is told to receive it warmly', C.mood_now()['v'] > 0.3 and 'искренне' in C.listen_block())
fresh(); C.sense('мне грустно'); ok('his sadness: she is told to stay beside him first, not to fix', 'побудь рядом' in C.listen_block())
fresh(); C.sense('я устал'); ok('his tiredness: softer and shorter', 'мягче' in C.listen_block())
fresh(); C.MEMORY['sensed'] = {'t': C.time.time() - 3600, 'tone': 'sad'}
ok('an old tone is not carried into later talk', C.listen_block() == '')
fresh(); M['hurt'] = {'t': C.time.time() - 4 * 3600, 'text': 'x'}
ok('an offence is forgotten after a few hours', C.listen_block() == '')
ok('persona text allows disagreement, advice, hurt and thanks', all(w in C.persona_block() for w in ('не согласиться', 'Советуй', 'обидеться', 'благодари')))
ok('...and keeps her warm', 'тёплой' in C.persona_block())

# survives a restart; hostile data does not break loading
fresh(); C.sense('идиот'); C.save_memory(); M['hurt'] = {'t': 0, 'text': ''}; C.load_memory()
ok('the offence is saved and reloaded', M['hurt']['t'] > 0)
for bad in ({'hurt': 'x'}, {'hurt': {'t': 'a', 'text': 1}}, {'hurt': {'t': 5, 'text': 'z' * 999}}):
    C.MEMORY_FILE.write_text(json.dumps(bad), encoding='utf-8'); M['hurt'] = {'t': 0, 'text': ''}
    try: C.load_memory(); r = True
    except Exception: r = False
    ok('damaged "hurt" does not break loading', r and len(M['hurt']['text']) <= 120)

# the real prompt and the real turn
seen = {}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    seen['system'] = m[0]['content']; yield '[sad] Мне было неприятно это слышать.'
app.generate_stream = fake
srv = ThreadingHTTPServer(('127.0.0.1', 8799), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(d):
    r = urllib.request.Request('http://127.0.0.1:8799/chat', json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    with urllib.request.urlopen(r) as x: return x.read().decode()
fresh()
post({'message': 'ты просто тупая железка'})
ok('the creator\'s rudeness reaches her prompt in the same turn', 'груб' in seen['system'] and 'не согласиться' in seen['system'])
ok('the prompt teaches her to write laughter and sighs as sounds', 'Ха-ха-ха' in seen['system'] and 'Эх' in seen['system'])
post({'initiative': 'idle'})
ok('her own initiative does not read tone from a service note', M['sensed']['tone'] == 'rude')
fresh()
post({'message': 'расскажи что-нибудь'})
ok('a calm message leaves no tone hint', 'Тон его последних слов' not in seen['system'])

# ---- her mood has causes she can name, shows in how she talks, and her views are not dropped for peace ----
import time as _t
from luna.core import convo
def clean():
    fresh(); M['mood_why'] = []
clean(); C.sense('ты тупая, заткнись')
b = C.mood_block()
ok('a mood has a cause: the rudeness is named', 'Что на это повлияло' in b and 'был груб со мной' in b and 'не придумывай другой' in b)
clean(); ok('no cause, no claim', 'Что на это повлияло' not in C.mood_block())
clean(); C.sense('спасибо тебе огромное'); ok('thanks is a cause too', 'поблагодарил' in C.mood_block())
clean(); C.sense('какая погода'); ok('a neutral message gives no cause', C.mood_why() == [])
clean(); C.shift_mood(-0.1, -0.1, 'его долго не было, и я скучала')
M['mood_why'][0]['t'] -= 9 * 3600
ok('an old cause is not offered as the reason any more', C.mood_why() == [] and 'Что на это повлияло' not in C.mood_block())
clean()
for i in range(10): C.shift_mood(0.01, 0, 'причина %d' % i)
ok('only a few recent causes are kept', len(M['mood_why']) == C.WHY_LIMIT and len(C.mood_why()) == 3 and C.mood_why()[-1][0] == 'причина 9')
clean(); C.sense('ты тупая'); C.save_memory(); C.MEMORY['mood_why'] = []; C.load_memory()
ok('causes survive a restart', any('груб' in w for w, _ in C.mood_why()))
M['mood_why'] = [{'t': 'x', 'why': 5, 'dv': 'q'}, 3, {'t': 1.0, 'why': ' ', 'dv': 0.1}]; C.save_memory(); C.load_memory()
ok('damaged causes are dropped on load', M['mood_why'] == [])

TXT = 'расскажи что-нибудь интересное про свой вечер'
ok('tired: shorter and quieter', 'вялая и сонная' in convo.hints([], TXT, hour=14, mood={'v': 0.2, 'e': 0.1}))
ok('low spirits: no forced cheer', 'не в духе' in convo.hints([], TXT, hour=14, mood={'v': -0.5, 'e': 0.5}))
ok('on a high: livelier', 'в ударе' in convo.hints([], TXT, hour=14, mood={'v': 0.8, 'e': 0.9}))
ok('an even mood adds nothing', all(w not in convo.hints([], TXT, hour=14, mood={'v': 0.2, 'e': 0.5}) for w in ('вялая', 'не в духе', 'в ударе')))
ok('no mood given: as before', 'вялая' not in convo.hints([], TXT, hour=14))
ok('pushback on a settled view: she does not cave for peace', 'Не сдавайся ради мира' in convo.hints([], 'нет, ты не права, это скучное кино', hour=14, held=True))
ok('pushback without a view: the plain correction hint stays', 'ошиблась' in convo.hints([], 'нет, ты ошиблась, это не так работает', hour=14) and 'ради мира' not in convo.hints([], 'нет, ты ошиблась, это не так работает', hour=14))

# ---- quiet moods are not joked away; her own views come back to her ----
rl = lambda n: (lambda s: n if isinstance(s, range) else list(s)[0])
low, fine = {'v': -0.5, 'e': 0.5}, {'v': 0.2, 'e': 0.5}
ok('idle in a low mood: quiet, not a joke', convo.idle_prompt('про аниме', ['просто'], rl(0), mood=low) == convo.LOW_IDLE[0])
ok('idle when tired: quiet too', convo.idle_prompt('', ['просто'], rl(3), mood={'v': 0.3, 'e': 0.1}) == convo.LOW_IDLE[0])
ok('idle in an even mood: as before', convo.idle_prompt('про аниме', ['просто'], rl(0), mood=fine) == convo.WEIRD[0])
ok('idle in a low mood: the high rolls are still the general prompts', convo.idle_prompt('', ['просто'], rl(9), mood=low) == 'просто')
vp = convo.idle_prompt('', ['просто'], rl(9), mood=fine, views=['космос: завораживает'])
ok('idle: a view of her own comes back', 'космос: завораживает' in vp and 'что думает он' in vp)
ok('idle: no views, no such prompt', convo.idle_prompt('', ['просто'], rl(9), mood=fine, views=[]) == 'просто')


# ---- days together: a round number is said warmly once, an old date is skipped quietly ----
import time as _t
_day = 86400
M['born'] = _t.time() - 30 * _day; M['milestone'] = 7
_h = C.milestone_note()
ok('30 days together: a warm hint, once', '30 дн.' in _h and M['milestone'] == 30)
ok('the same date is not said twice', C.milestone_note() == '')
M['born'] = _t.time() - 101 * _day; M['milestone'] = 30
ok('a date just passed (a day or two late) is still said', '100 дн.' in C.milestone_note())
M['born'] = _t.time() - 150 * _day; M['milestone'] = 30
ok('an old date is skipped quietly and remembered', C.milestone_note() == '' and M['milestone'] == 100)
M['born'] = _t.time() - 366 * _day; M['milestone'] = 200
ok('a year together', 'год' in C.milestone_note())
M['born'] = _t.time() - 731 * _day; M['milestone'] = 365
ok('two years together', '2 г.' in C.milestone_note())
M['born'] = _t.time() - 3 * _day; M['milestone'] = 0
ok('before the first week: nothing', C.milestone_note() == '')
M['born'] = 0
ok('no birth date: nothing, no crash', C.milestone_note() == '')
M['born'] = _t.time() - 8 * _day; M['milestone'] = 0; M['late'] = 0; M['moments'] = []
ok('the greeting care carries the milestone', '7 дн.' in C.care_note())


# memory recall in Japanese: no spaces, so the stems are pairs of letters, and the fitting fact is chosen
M['user'] = ['猫の名前はミケで、毎朝一緒に散歩に行く', '仕事は東京のデザイン会社で働いている', '好きな食べ物は寿司と焼き鳥です', '妹は大学で医学を勉強している', '週末はよく映画を見に行く',
             '夏に北海道へ旅行する予定がある', 'コーヒーよりお茶のほうが好き', '朝は六時に起きるようにしている', '最近ギターを習い始めた', '父は釣りが趣味で毎週川へ行く',
             '誕生日は十一月の終わり', '眼鏡をかけていて視力が悪い', '高校のときは野球部だった']
ok('stems of Japanese are pairs of letters', 'ミケ' in C.stem('ミケです') and 'です' not in C.stem('ミケです'))
ok('Japanese recall: the cat question finds the cat fact', any('ミケ' in f for f in C.recall('user', '猫の名前を覚えてる？', k=3)))
ok('Japanese recall: a trip question finds the trip fact', any('北海道' in f for f in C.recall('user', '旅行はどこに行くんだっけ', k=3)))
ok('Russian stems still work', C.stem('собака') & C.stem('собаку'))
