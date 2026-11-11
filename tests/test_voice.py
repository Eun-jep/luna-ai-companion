"""Intonation: voice.shape() and the /tts endpoint (the speech service itself is faked, so no network and no sound)."""
import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.core import voice
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
S = voice.shape

ok('standalone module', 'app' not in sys.modules and 'character' not in sys.modules)
n = S('Привет.')
ok('neutral plain line is untouched', (n['text'], n['rate'], n['pitch'], n['volume']) == ('Привет.', 0, 0, 0))
h, s, a, sh = S('Привет.', 'happy'), S('Привет.', 'sad'), S('Привет.', 'angry'), S('Привет.', 'shy')
ok('happy is brighter and faster than neutral', h['pitch'] > 0 and h['rate'] > 0)
ok('sad is lower, slower and quieter', s['pitch'] < 0 and s['rate'] < 0 and s['volume'] < 0)
ok('angry is louder', a['volume'] > 0 and a['pitch'] < h['pitch'])
ok('shy is quiet', sh['volume'] < 0)
ok('every emotion of the avatar has a voice', set(voice.PROSODY) >= {'neutral', 'happy', 'sad', 'angry', 'surprised', 'shy', 'love', 'confused', 'excited'})
ok('unknown emotion falls back to neutral', S('Да.', 'bogus')['pitch'] == 0)

lively, tired = {'v': 0.8, 'e': 0.9}, {'v': -0.6, 'e': 0.1}
ok('a lively glad mood speaks brighter and faster than a tired low one', S('Да.', 'neutral', lively)['pitch'] > S('Да.', 'neutral', tired)['pitch']
   and S('Да.', 'neutral', lively)['rate'] > S('Да.', 'neutral', tired)['rate'])
ok('night is quieter and slower', S('Да.', 'neutral', None, 3)['volume'] < S('Да.', 'neutral', None, 14)['volume'] and S('Да.', 'neutral', None, 23)['rate'] < 0)

ok('"!" lifts, "?" rises, "..." slows',
   S('Да!')['pitch'] > S('Да.')['pitch'] and S('Да?')['pitch'] > S('Да.')['pitch'] and S('Да...')['rate'] < S('Да.')['rate'])

l = S('Ха-ха-ха!')
ok('laughter is split into bursts', l['text'] == 'Ха, ха, ха!')
ok('laughter sounds brighter and quicker', l['pitch'] > S('Да!')['pitch'] and l['rate'] > S('Да!')['rate'])
ok('laughter inside a sentence keeps the rest', S('Ну ты даёшь, хахаха, правда!')['text'].startswith('Ну ты даёшь, ха, ха, ха'))
ok('English laughter', S('Haha, that is funny')['text'].startswith('Ha, ha'))
ok('"ха" in ordinary words is not laughter', S('Хорошо, хотя нет, ухо болит.')['text'] == 'Хорошо, хотя нет, ухо болит.')
ok('a single "he" or "ha" is not laughter', S('He said ha.')['text'] == 'He said ha.')
ok('sigh slows and lowers', S('Эх... ладно.')['rate'] < 0 and S('Эх... ладно.')['pitch'] < 0)
ok('empty text does not crash', S('')['text'] == '')
big = S('Ха-ха-ха!', 'excited', {'v': 1, 'e': 1})
ok('values stay in the service limits', all(voice.LIMITS[k][0] <= big[k] <= voice.LIMITS[k][1] for k in ('rate', 'pitch', 'volume')))

# the endpoint passes the shaped values to the speech service
import app
from luna.core import character
tmp = pathlib.Path(tempfile.mkdtemp()); character.MEMORY_FILE = tmp / 'memory.json'; app.load_memory()
seen = {}
def fake(text, v, rate=0, pitch=0, volume=0):
    seen.update(text=text, rate=rate, pitch=pitch, volume=volume); return b'ID3fake'
app.synthesize = fake
app.edge_tts = object()
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8798), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(d):
    r = urllib.request.Request('http://127.0.0.1:8798/tts', json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
c, b = post({'text': 'Ха-ха-ха! Это было смешно.', 'emotion': 'happy', 'rate': 0, 'pitch': 0})
ok('endpoint: audio comes back', c == 200 and b == b'ID3fake')
ok('endpoint: text is shaped (laughter), happy raises the pitch', seen['text'].startswith('Ха, ха, ха') and seen['pitch'] > 0 and seen['rate'] > 0)
post({'text': 'Мне грустно.', 'emotion': 'sad', 'rate': 0, 'pitch': 0})
ok('endpoint: sad is slower, lower and quieter', seen['rate'] < 0 and seen['pitch'] < 0 and seen['volume'] < 0)
post({'text': 'Привет.', 'emotion': 'neutral', 'rate': 40, 'pitch': 90})
ok('endpoint: the user\'s own settings are added and clamped', seen['rate'] <= 50 and seen['pitch'] <= 100 and seen['rate'] >= 35)
c, _ = post({'text': 'Привет.', 'emotion': 5, 'rate': 0, 'pitch': 0})
ok('endpoint: junk emotion is harmless', c == 200)
ok('endpoint: bad settings refused', post({'text': 'x', 'rate': 'a', 'pitch': 0})[0] == 400)

# the end of a line changes the voice in Japanese too: the full-width marks count like the ASCII ones
_flat = voice.shape('そうなんだ。')
ok('full-width ！ raises the voice like !', voice.shape('すごい！')['pitch'] > _flat['pitch'] and voice.shape('すごい！')['pitch'] == voice.shape('wow!')['pitch'])
ok('full-width ？ raises the pitch like ?', voice.shape('本当に？')['pitch'] > _flat['pitch'] and voice.shape('本当に？')['pitch'] == voice.shape('really?')['pitch'])
ok('… slows down like ...', voice.shape('うーん……')['rate'] < _flat['rate'] and voice.shape('だよね…')['rate'] == voice.shape('well...')['rate'])
