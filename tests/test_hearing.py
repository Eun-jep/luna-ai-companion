"""Hearing the speakers (hearing.py + /hear + media from sound). All with fakes:
no real capture, no model, no network."""
import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error, zipfile, io, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import hearing, media, voice
_real_listen = hearing.listen   # a later part of this file replaces listen with a fake
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

rng = np.random.default_rng(1)
SR = hearing.SR
t = np.arange(SR * 3) / SR
silence = np.zeros(SR * 3, dtype=np.float32)
hum = (0.001 * rng.standard_normal(SR * 3)).astype(np.float32)
calm = (0.015 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
loud = (0.4 * np.sign(np.sin(2 * np.pi * 3000 * t)) * (np.sin(2 * np.pi * 4 * t) > 0)).astype(np.float32)

# ---- understanding sound ----
ok('silence', hearing.classify(silence)['kind'] == 'silence' and hearing.classify(hum)['kind'] == 'silence')
c = hearing.classify(calm)
ok('sound without words is music, with its character', c['kind'] == 'music' and 'тихая' in c['about'])
l = hearing.classify(loud)
ok('loud bright pulsing sound is described that way', l['kind'] == 'music' and 'громкая' in l['about'] and 'ритмичным' in l['about'])
words = ('привет как твои дела сегодня', 0.05, -0.1)
v = hearing.classify(calm, words)
ok('understood words: voice with the words', v['kind'] == 'voice' and 'как твои дела' in v['text'] and 'слышны слова' in v['about'])
ok('few words or low confidence: still music', hearing.classify(calm, ('да', 0.1, -0.1))['kind'] == 'music' and hearing.classify(calm, (words[0], 0.9, -0.1))['kind'] == 'music')
ok('long text is cut', len(hearing.classify(calm, ('слово ' * 300, 0.1, -0.1))['text']) <= hearing.MAX_TEXT)
ok('tiny or odd input does not crash', hearing.features(np.zeros(3))['rms'] == 0 and hearing.classify(np.zeros(0))['kind'] == 'silence')

# ---- privacy ----
for title in ['Zoom Meeting', 'Microsoft Teams', 'Discord | #general', 'Telegram', 'Встреча - Google Meet', 'Созвон с командой']:
    ok('no listening in a call or messenger: ' + title, hearing.is_private(title))
ok('a film window is not private', not hearing.is_private('Stranger Things | Netflix - Google Chrome') and not hearing.is_private(None))

# ---- listen() with fakes ----
hearing.reset(); hearing._state.update(status='ready', error=''); hearing._lang = 'ru'
calls = []
hearing._capture = lambda seconds=hearing.SECONDS: calls.append(1) or calm
hearing._asr = lambda a: words
r = hearing.listen('ru')
ok('listen: result kept and fresh', r['kind'] == 'voice' and hearing.fresh() is r and len(calls) == 1)
ok('an old result is not "now"', hearing.fresh(time.time() + hearing.FRESH + 5) is None)
hearing.mute(30)
ok('muted (her own voice): she does not listen at all', hearing.listen('ru') is None and len(calls) == 1)
hearing.reset()
ok('reset forgets', hearing.fresh() is None and not hearing.muted())
def capture_while_she_speaks(seconds=0):
    hearing.mute(10); return calm
hearing._capture = capture_while_she_speaks
ok('she started speaking during the listen: it was her, discarded', hearing.listen('ru') is None and hearing.fresh() is None)
hearing.reset(); hearing._capture = lambda seconds=0: silence
asr_calls = []
hearing._asr = lambda a: asr_calls.append(1) or words
ok('silence: the recognizer is not even run', hearing.listen('ru')['kind'] == 'silence' and not asr_calls and hearing.fresh() is None)
hearing.reset()
def boom(seconds=0): raise OSError('no loopback device')
hearing._capture = boom
ok('a broken device is reported, not raised', hearing.listen('ru') is None and 'OSError' in hearing.state()['error'])
hearing._state['status'] = 'idle'; hearing._capture = lambda seconds=0: calm
ok('no recognizer yet: nothing recorded', hearing.listen('ru') is None)
hearing._state['status'] = 'ready'; hearing._lang = 'en'
ok('wrong language model loaded: nothing recorded', hearing.listen('ru') is None)

# ---- model download safety ----
try: hearing._download('https://evil.example/model.zip', pathlib.Path(tempfile.mkdtemp()) / 'x.zip'); bad = True
except ValueError: bad = False
ok('only the official model site is accepted', not bad)
ok('both languages point at the official site', all(u.startswith('https://alphacephei.com/vosk/models/') for _, u in hearing.MODELS.values()))
tmp = pathlib.Path(tempfile.mkdtemp())
evil = tmp / 'evil.zip'
with zipfile.ZipFile(evil, 'w') as z: z.writestr('../escape.txt', 'x')
try: hearing._unpack(evil, tmp / 'out'); bad = True
except ValueError: bad = False
ok('a zip that tries to leave its folder is refused', not bad and not (tmp / 'escape.txt').exists())
good = tmp / 'good.zip'
with zipfile.ZipFile(good, 'w') as z: z.writestr('model/a.txt', 'x')
hearing._unpack(good, tmp / 'out2')
ok('a normal archive unpacks', (tmp / 'out2' / 'model' / 'a.txt').is_file())

# ---- media from sound ----
ok('no title: sound becomes a topic', media.from_sound({'kind': 'music', 'text': '', 'about': 'играет музыка (тихая)'})['kind'] == 'sound')
ok('silence is nothing', media.from_sound({'kind': 'silence'}) is None and media.from_sound(None) is None)
s = media.from_sound({'kind': 'voice', 'text': 'Привет как твои дела', 'about': 'слышны слова: «x»'})
p = media.prompt(s)
ok('prompt: she hears it herself, knows no title, does not invent, may stay quiet', 'слышишь' in p and 'не выдумывай' in p and '[quiet]' in p and 'Названия ты не знаешь' in p)
info = media.detect('Frieren - AniLibria - Opera')
both = media.prompt(info, heard={'kind': 'music', 'about': 'играет музыка (громкая)'})
ok('a known title plus what she hears', 'Frieren' in both and 'играет музыка (громкая)' in both)

# ---- the server ----
import app, character
character.MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'; app.load_memory()
import audit; audit.FILE = pathlib.Path(tempfile.mkdtemp()) / 'journal.jsonl'   # the real journal is never written by a test
seen = {}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    seen['last'] = m[-1]['content'] if isinstance(m[-1]['content'], str) else m[-1]['content'][-1]['text']
    yield '[happy] Ого, как круто звучит!'
app.generate_stream = fake
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8801), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d):
    r = urllib.request.Request('http://127.0.0.1:8801' + path, json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
def jpost(path, d):
    c, b = post(path, d)
    try: return c, json.loads(b)
    except ValueError: return c, b

req = urllib.request.Request('http://127.0.0.1:8801/hear', b'{}', {'Content-Type': 'application/json'})
try: urllib.request.urlopen(req); code = 200
except urllib.error.HTTPError as e: code = e.code
ok('/hear needs the app token', code == 403)

hearing.available = lambda: {'capture': True, 'asr': False}
c, r = jpost('/hear', {'on': True})
ok('missing pieces: 501 with what is missing', c == 501 and r['need'] == ['asr'])
hearing.available = lambda: {'capture': True, 'asr': True}
hearing.reset(); hearing._state.update(status='ready', error=''); hearing._lang = 'ru'
hearing._capture = lambda seconds=0: calm; hearing._asr = lambda a: words
c, r = jpost('/hear', {'on': True, 'window': 'Zoom Meeting', 'lang': 'ru'})
ok('a call window: nothing is listened to', r['kind'] == 'private' and hearing.fresh() is None)
c, r = jpost('/hear', {'on': True, 'window': 'Stranger Things | Netflix - Google Chrome', 'lang': 'ru'})
ok('listens and says only the kind (no text goes to the page)', c == 200 and r['kind'] == 'voice' and 'слов' not in json.dumps(r, ensure_ascii=False) and hearing.fresh())
prepared = []
hearing.prepare = lambda lang='ru': prepared.append(lang)
c, r = jpost('/hear', {'on': True, 'lang': 'en'})
ok('another language: the recognizer is (re)prepared, nothing recorded yet', r['kind'] == '' and prepared == ['en'])
c, r = jpost('/hear', {'on': False})
ok('off: forgets what she heard', c == 200 and hearing.fresh() is None)
c, r = jpost('/hear', {'on': 'yes'})
ok('only a real true switches it on', c == 200 and r == {'ok': True})

# comment from sound alone
hearing._state.update(status='ready'); hearing._lang = 'ru'; hearing.reset()
hearing._capture = lambda seconds=0: calm; hearing._asr = lambda a: words
hearing.listen('ru'); media.reset(); seen.clear()
c, _ = post('/chat', {'initiative': 'media', 'window': ''})
ok('initiative from sound alone: she is told what she hears', c == 200 and 'слышишь' in seen['last'] and 'как твои дела' in seen['last'])
seen.clear()
c, _ = post('/chat', {'initiative': 'media', 'window': ''})
ok('and not again right away', c == 400 and not seen)
hearing.reset(); media.reset(); seen.clear()
c, _ = post('/chat', {'initiative': 'media', 'window': ''})
ok('heard nothing: she keeps quiet, the model is not called', c == 400 and not seen)
hearing.listen('ru'); seen.clear()
c, _ = post('/chat', {'message': 'как тебе?', 'media': 'Frieren - AniLibria - Opera'})
ok('in a chat she knows both the title and the sound', c == 200 and 'Frieren' in seen['last'] and 'слышны слова' in seen['last'])

# her own voice mutes hearing
hearing.reset()
class FakeEdge:
    class Communicate:
        def __init__(self, *a, **k): pass
        async def stream(self):
            yield {'type': 'audio', 'data': b'ID3fake'}
app.edge_tts = FakeEdge
c, b = post('/tts', {'text': 'Привет, как дела у тебя сегодня?', 'rate': 0, 'pitch': 0})
ok('/tts mutes hearing while she talks', c == 200 and hearing.muted())

hearing.reset()

# ---- he asks: "do you hear it?" ----
hearing.available = lambda: {'capture': True, 'asr': True}
hearing._state.update(status='ready', error=''); hearing._lang = 'ru'; hearing._capture = lambda seconds=0: calm; hearing._asr = lambda a: ('', 1.0, -9.0)
post('/chat', {'message': 'ты слышишь музыку что играет?', 'lang': 'ru'})
ok('setting off: she is told it is off, no invented excuses', 'выключен' in seen['last'] and 'нет колонок' in seen['last'])
post('/chat', {'message': 'ты слышишь музыку что играет?', 'lang': 'ru', 'hear': True, 'media': 'LIFE - Neuro-sama (Official Video) - YouTube'})
ok('setting on: she listens now and gets what is playing and the window title', 'прислушалась' in seen['last'] and 'играет музыка' in seen['last'] and 'LIFE - Neuro-sama' in seen['last'] and 'название не зна' in seen['last'])
hearing.reset(); hearing._capture = lambda seconds=0: silence
post('/chat', {'message': 'слышишь что-нибудь?', 'lang': 'ru', 'hear': True})
ok('silence: she says she hears nothing', 'тишина' in seen['last'])
hearing.reset(); hearing._capture = lambda seconds=0: calm
post('/chat', {'message': 'слышишь музыку?', 'lang': 'ru', 'hear': True, 'media': 'Zoom Meeting'})
ok('a call window: she does not listen', 'не слушаешь' in seen['last'])
post('/chat', {'message': 'как дела?', 'lang': 'ru', 'hear': True})
ok('an ordinary question does not make her listen', 'прислушалась' not in seen['last'] and 'выключен' not in seen['last'])
hearing.reset(); hearing._capture = lambda seconds=0: calm; hearing.mute(0.8)
post('/chat', {'message': 'слышишь музыку?', 'lang': 'ru', 'hear': True})
ok('her own voice in the way: she waits it out and then listens', 'играет музыка' in seen['last'])
hearing.reset(); hearing._state['error'] = ''
def broken(seconds=0): raise OSError('no loopback')
hearing._capture = broken
post('/chat', {'message': 'слышишь музыку?', 'lang': 'ru', 'hear': True})
ok('a failed listen is not reported as silence', 'не вышло' in seen['last'] and 'OSError' in seen['last'] and 'тишина' not in seen['last'].split('не вышло')[0][-20:])

# "remember my choice": a separate opt-in, off by default, never restores hearing without both flags
js = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'web', 'app.js'), encoding='utf-8').read()
html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'index.html'), encoding='utf-8').read()
i18n = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'web', 'i18n.js'), encoding='utf-8').read()
ok('hearkeep checkbox is off by default', 'id="hearkeep"' in html and 'id="hearkeep" checked' not in html)
ok('hearing returns only with both flags saved', 'saved.hearkeep === true && saved.hearon === true' in js)
ok('hearon is saved only when the keep box is ticked', "$('#hearkeep').checked && $('#hear')" in js)
ok('hearkeep in all four languages', i18n.count("hearkeep: '") == 4 and i18n.count("'hearkeep.d'") == 4)

# song by its words: only text goes to a search, only when he asks, only without a window title
words = {'kind': 'voice', 'text': 'мы вышли в ночь под звёздным небом [ой] и тихо', 'about': 'слышны слова'}
hearing.reset(); hearing._capture = lambda seconds=0: calm
hearing.listen = lambda lang=None, *a, **k: dict(words)
post('/chat', {'message': 'что это за песня?', 'lang': 'ru', 'hear': True, 'agent': True})
ok('song question with words: she is told to search by the words', '[web:мы вышли в ночь' in seen['last'] and 'песня текст' in seen['last'])
ok('brackets of the lyrics never reach the search command', '[ой]' not in seen['last'] and '[web:мы вышли в ночь под звёздным небом ой и тихо песня' in seen['last'])
post('/chat', {'message': 'что это за песня?', 'lang': 'ru', 'hear': True, 'agent': False})
ok('without the web helper no search is asked', '[web:мы' not in seen['last'])
post('/chat', {'message': 'что это за песня?', 'lang': 'ru', 'hear': True, 'agent': True, 'media': 'Artist - Title - YouTube'})
ok('a window title wins: no lyric search', '[web:мы' not in seen['last'] and 'Artist - Title' in seen['last'])
words['text'] = 'ла ла'
post('/chat', {'message': 'что это за песня?', 'lang': 'ru', 'hear': True, 'agent': True})
ok('too few words: honest, no search', 'название не знаешь'.split()[0] in seen['last'] and '[web:ла' not in seen['last'])
post('/chat', {'message': 'как дела?', 'lang': 'ru', 'hear': True, 'agent': True})
ok('an ordinary question never searches lyrics', 'Поищи по этим словам' not in seen['last'])

# the same song twice: the second time she answers from memory, no new search
character.MEMORY['learned'] = []
words['text'] = 'мы вышли в ночь под звёздным небом и тихо'
post('/chat', {'message': 'что это за песня?', 'lang': 'ru', 'hear': True, 'agent': True})
ok('first time: she searches', '[web:мы вышли в ночь' in seen['last'])
character.learn('мы вышли в ночь под звёздным небом и тихо песня текст исполнитель', 'По словам это похоже на песню «Ночь» группы Север, но я не уверена.')
words['text'] = 'мы вышли в ночь под звёздным небом'
post('/chat', {'message': 'а что это за песня играет?', 'lang': 'ru', 'hear': True, 'agent': True})
ok('second time: she answers from memory and does not search again', 'Ночь» группы Север' in seen['last'] and 'Заново искать не нужно' in seen['last'] and '[web:мы вышли' not in seen['last'])
words['text'] = 'совсем другие слова про море и корабли вдали'
post('/chat', {'message': 'что это за песня?', 'lang': 'ru', 'hear': True, 'agent': True})
ok('other words: a new search', '[web:совсем другие слова' in seen['last'])

# Russian microphone: the exact recognizer (GigaAM) takes the sentence when it is loaded, plain Vosk streams otherwise
class FakeGiga:
    def create_stream(self): return None
saved = (hearing._model, hearing._lang, hearing._exact)
vdir = hearing.MODEL_DIR / hearing.MODELS['ru'][0]
if vdir.is_dir():
    import vosk
    hearing._model, hearing._lang, hearing._exact = vosk.Model(str(vdir)), 'ru', None
    ok('ru microphone without the exact model: the plain Vosk stream', type(hearing._new_stream()).__name__ == 'Stream')
    hearing._exact = FakeGiga()
    st = hearing._new_stream()
    ok('ru microphone with the exact model: the sentence goes through it (SenseStream over GigaAM)', type(st).__name__ == 'SenseStream' and st.rec is hearing._exact)
    hearing._lang = 'en'
    ok('english has an exact microphone recognizer too', type(hearing._new_stream()).__name__ == 'SenseStream')
    hearing._lang = 'ko'
    ok('other languages do not take the ru/en recognizer', type(hearing._new_stream()).__name__ == 'Stream')
hearing._model, hearing._lang, hearing._exact = saved

# tidied text, her names, and how it was said
ok('ru: joined words get their hyphen', hearing.tidy('дай чтонибудь коечто изза этого и всетаки', 'ru') == 'дай что-нибудь кое-что из-за этого и все-таки')
ok('ru: ordinary words are not touched', hearing.tidy('это то что нужно, никто не знает', 'ru') == 'это то что нужно, никто не знает')
ok('en: a number glued to a word gets its space, names with digits stay', hearing.tidy('at6 in the evening, mp3 and gpt4', 'en') == 'at 6 in the evening, mp3 and gpt4')
names = ['Дмитрий', 'Андрей', 'Настя', 'Сеул', 'Катерина']
ok('a one-letter slip becomes his own name', hearing.vocab_fix('мы видели дмитрей вчера', names) == 'мы видели Дмитрий вчера')
ok('a case form of a name is left alone', hearing.vocab_fix('я звонил андрея и настю', names) == 'я звонил андрея и настю')
ok('an ordinary word and short names are left alone', hearing.vocab_fix('это каталог и каша', names + ['Катя']) == 'это каталог и каша')
ok('no vocabulary: no change', hearing.vocab_fix('дмитрей', []) == 'дмитрей')
saved_src = hearing.VOCAB_SOURCE
hearing.VOCAB_SOURCE = lambda: names
ok('refine uses the vocabulary', hearing.refine('позвони дмитрей', 'ru') == 'позвони Дмитрий')
def boom(): raise RuntimeError('x')
hearing.VOCAB_SOURCE = boom
ok('a failing vocabulary never costs the sentence', hearing.refine('позвони дмитрей', 'ru') == 'позвони дмитрей')
hearing.VOCAB_SOURCE = saved_src

def said(level, secs, words, quiet_after=0.5):
    p = hearing.Prosody()
    for _ in range(3): p.feed(np.full(1600, 0.002, dtype=np.float32))
    for i in range(int(secs * 10)): p.feed((np.sin(np.arange(1600) / 5) * level).astype(np.float32))
    for _ in range(int(quiet_after * 10)): p.feed(np.full(1600, 0.002, dtype=np.float32))
    return p.describe(words)
hearing._usual.clear()
ok('the first sentences only build his usual: nothing is said', all(said(0.2, 2.5, 7) == '' for _ in range(4)))
ok('the same as usual: nothing', said(0.2, 2.5, 7) == '')
ok('quieter and slower than his usual is named', said(0.05, 4.0, 5) == 'тише обычного, медленнее обычного')
ok('louder and faster is named', said(0.5, 1.5, 9) == 'громче обычного, быстрее обычного')
ok('a very short phrase says nothing', said(0.05, 0.5, 2) == '')

# ---- which song, by its sound (opt-in; a fingerprint, not the sound, goes to the outside service) ----
import songid
hearing.listen = _real_listen
ok('the sound is kept for a moment only when asked, taken once, then gone', True)
hearing.reset(); hearing._state.update(status='ready', error=''); hearing._lang = 'ru'
hearing._capture = lambda seconds=0: calm; hearing._asr = lambda a: ('', 1.0, -9.0)
hearing.listen('ru'); ok('not kept by default', hearing.take_audio() is None)
hearing.listen('ru', keep=True); got = hearing.take_audio()
ok('kept on request', got is not None and len(got) == len(calm)); ok('and only once', hearing.take_audio() is None)
asked = []
songid.available = lambda: True
songid.identify = lambda a, timeout=25: asked.append(len(a)) or {'title': 'Ночь', 'artist': 'Север'}
ASK = {'message': 'что это за песня играет?', 'lang': 'ru', 'hear': True}
post('/chat', dict(ASK, songid=True))
ok('on and asked: the fingerprint service answer reaches her as data', asked and 'Shazam' in seen['last'] and 'название «Ночь»' in seen['last'] and 'исполнитель «Север»' in seen['last'] and 'не указания' in seen['last'])
n = len(asked)
post('/chat', ASK)
ok('off (the default): nothing is sent anywhere', len(asked) == n and 'Shazam' not in seen['last'])
post('/chat', dict(ASK, songid=True, media='LIFE - Neuro-sama (Official Video) - YouTube'))
ok('the window already names it: no service is asked', len(asked) == n)
post('/chat', dict(ASK, message='слышишь музыку?', songid=True))
ok('not asked about a song: no service is asked', len(asked) == n)
songid.identify = lambda a, timeout=25: None
post('/chat', dict(ASK, songid=True))
ok('no match: she is told to say so honestly', 'опознать не удалось' in seen['last'] and 'Shazam назвал' not in seen['last'])
ok('the sound is not kept after the answer', hearing.take_audio() is None)
ok('journal says it happened, without the title', any(e['kind'] == 'songid' and 'Ночь' not in json.dumps(e, ensure_ascii=False) for e in __import__('audit')._read()))
ok('wav bytes are a real wav', songid.wav_bytes(np.zeros(1600))[:4] == b'RIFF')
ok('a title is cleaned of tag-like characters and cut', songid.clean('A [web:x] «B» ' + 'z' * 200) == 'A web:x B ' + 'z' * 70 or len(songid.clean('A [web:x] «B» ' + 'z' * 200)) <= 80 and '[' not in songid.clean('[x]'))
ok('no answer / odd answer: nothing recognized', songid.parse({}) is None and songid.parse({'track': 5}) is None and songid.parse({'track': {'title': ''}}) is None)


# ---- her own voice on the microphone is not him ----
import time as _time
hearing._said.clear()
_now = _time.time()
hearing.said('Привет, я так рада тебя видеть сегодня вечером, расскажи, как прошёл день', _now)
ok('echo: her own words coming back are recognised', hearing.echo_of_her('рада тебя видеть сегодня вечером', _now + 3))
ok('echo: a slightly mis-heard echo still counts', hearing.echo_of_her('так рада тебя видеть сегодня вечер', _now + 3))
ok('his own different sentence is not an echo', not hearing.echo_of_her('я хочу пить чай и лечь спать', _now + 3))
ok('a short phrase can be anyone: not an echo', not hearing.echo_of_her('рада тебя', _now + 3))
ok('a half of her words and half his is not an echo', not hearing.echo_of_her('рада тебя видеть а ещё хочу кофе очень сильно', _now + 3))
ok('after two minutes the echo window is closed', not hearing.echo_of_her('рада тебя видеть сегодня вечером', _now + 200))
hearing._said.clear()
hearing.said('오늘 날씨가 정말 좋네요 같이 산책 갈까요', _now)
ok('echo in Korean', hearing.echo_of_her('날씨가 정말 좋네요 같이 산책', _now + 2))
ok('his Korean sentence is not an echo', not hearing.echo_of_her('배고파서 라면 먹고 싶어요 지금', _now + 2))
hearing._said.clear()
hearing.said('今日はとてもいい天気ですね散歩に行きましょう', _now)
ok('echo in Japanese', hearing.echo_of_her('とてもいい天気ですね散歩に行きましょう', _now + 2))
ok('his Japanese sentence is not an echo', not hearing.echo_of_her('お腹がすいたのでラーメンを食べたい', _now + 2))
hearing._said.clear()
ok('nothing was said by her: nothing is an echo', not hearing.echo_of_her('рада тебя видеть сегодня вечером', _now))
hearing.said('Конечно, давай сходим в парк после обеда', _time.time())
_orig = hearing._listen_mic
hearing._listen_mic = lambda code, pros: 'давай сходим в парк после обеда'
ok('the microphone path drops her own voice (nothing said)', hearing.listen_mic('ru') == '')
hearing._listen_mic = lambda code, pros: 'нет, лучше останемся дома и посмотрим фильм'
ok('the microphone path keeps his own words', hearing.listen_mic('ru') == 'нет, лучше останемся дома и посмотрим фильм')
hearing._listen_mic = _orig
hearing._said.clear()


# Japanese has no spaces: heard speech is still counted in words, so it is "voice" and not music, and the pace means something
ok('count_words: Russian by spaces', hearing.count_words('привет как дела у тебя') == 5)
ok('count_words: a Japanese sentence is several words', hearing.count_words('今日はとてもいい天気ですね') >= 4)
ok('count_words: nothing is zero', hearing.count_words('') == 0)
_f = hearing.classify.__globals__['features']
import numpy as _np
_audio = (_np.random.RandomState(1).randn(16000 * 4) * 0.05).astype(_np.float32)
_res = hearing.classify(_audio, ('今日はとてもいい天気ですね散歩に行きましょう', 0.1, -0.2))
ok('Japanese heard speech is classified as voice, not music', _res['kind'] == 'voice')
