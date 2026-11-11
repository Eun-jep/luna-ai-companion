"""Speaking through the microphone locally (hearing.listen_mic + /listen, Agc) and the plain one-syllable voice of /tts. All with fakes: no real device, no model, no network."""
import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from luna.senses import hearing
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)


import app
from luna.core import character
character.MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'; app.load_memory()
mode = {'reply': []}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    mode['prompt'] = m[0]['content']
    for piece in mode['reply']:
        yield piece
app.generate_stream = fake
app.generate = lambda m: 'не умею'   # the separate request for words: nothing usable unless a test says otherwise
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8802), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d):
    r = urllib.request.Request('http://127.0.0.1:8802' + path, json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read()
    except urllib.error.HTTPError as e: return e.code, e.read()

# one flat syllable from /tts
seen = {}
class FakeEdge:
    class Communicate:
        def __init__(self, text, voice, rate='', pitch='', volume=''):
            seen.update(text=text, rate=rate, pitch=pitch, volume=volume)
        async def stream(self):
            yield {'type': 'audio', 'data': b'ID3fake'}
app.edge_tts = FakeEdge
c, b = post('/tts', {'text': 'при', 'rate': 0, 'pitch': 0, 'emotion': 'excited', 'plain': True})
ok('plain syllable: no intonation added', c == 200 and seen['text'] == 'при' and seen['rate'] == '+0%' and seen['pitch'] == '+0Hz' and seen['volume'] == '+0%')
c, b = post('/tts', {'text': 'Привет!', 'rate': 0, 'pitch': 0, 'emotion': 'excited'})
ok('ordinary speech still gets its intonation', c == 200 and seen['rate'] != '+0%')

# ---- the microphone, locally ----
class FakeRec:
    def __init__(self, loud_from, loud_until):
        self.n, self.a, self.b = 0, loud_from, loud_until
    def __enter__(self): return self
    def __exit__(self, *e): return False
    def record(self, numframes):
        self.n += 1
        amp = 0.2 if self.a <= self.n < self.b else 0.002
        return (amp * np.sin(np.linspace(0, 200, numframes))).astype(np.float32).reshape(-1, 1)
class FakeStream:
    """Stands in for the streaming recognizer: words once something loud came, a sentence end after a short quiet."""
    made = []
    def __init__(self): self.loud = 0; self.quiet = 0; self.fed = 0; FakeStream.made.append(self)
    def feed(self, pcm):
        a = np.frombuffer(pcm, dtype=np.int16)
        self.fed += 1
        if np.abs(a).max() > 3000: self.loud += 1; self.quiet = 0
        elif self.loud: self.quiet += 1
        return self.loud > 0 and self.quiet >= 5
    def partial(self): return 'привет' if self.loud and not self.quiet >= 5 else ''
    def result(self): return 'привет луна'
    def final(self): return 'привет'
hearing._state.update(status='ready', error=''); hearing._lang = 'ru'
hearing._new_stream = FakeStream
hearing._open_mic = lambda: FakeRec(4, 10)
ok('speech then a pause: the words come back at once', hearing.listen_mic('ru') == 'привет луна')
ok('it listens in tenths of a second', hearing.MIC_STEP == hearing.SR // 10)
ok('nothing is left over afterwards', hearing.mic_partial() == '')
seen = []
class Peek(FakeStream):
    def partial(self):
        p = super().partial(); seen.append(hearing.mic_partial()); return p
hearing._new_stream = Peek
hearing.listen_mic('ru')
ok('the words so far are available while she listens', 'привет' in seen)
hearing._new_stream = FakeStream
hearing._open_mic = lambda: FakeRec(10 ** 6, 10 ** 6 + 1)
hearing.MIC_WAIT = 0.0
ok('nobody speaks: empty text', hearing.listen_mic('ru') == '')
hearing.MIC_WAIT = 7.0
hearing._open_mic = lambda: FakeRec(4, 10)
ok('wrong language model: not ready', hearing.listen_mic('en') is None)
hearing._state['status'] = 'loading'
ok('model not ready: not ready', hearing.listen_mic('ru') is None)
hearing._state['status'] = 'ready'
class Cancelling(FakeRec):
    def record(self, numframes):
        hearing.cancel_mic(); return super().record(numframes)
hearing._open_mic = lambda: Cancelling(4, 10)
ok('cancelled while listening: None', hearing.listen_mic('ru') is None)
quiet = hearing.Agc()
room = [quiet(np.full(1600, 0.002, dtype=np.float32)) for _ in range(5)]
ok('the room noise is not made into speech level', max(float(np.abs(r).max()) for r in room) < 0.08)
voice = [quiet((0.02 * np.sin(np.linspace(0, 50, 1600))).astype(np.float32)) for _ in range(6)]
ok('a quiet voice is raised to a usable level', float(np.abs(voice[-1]).max()) > 0.15)
loud = quiet((0.5 * np.sin(np.linspace(0, 50, 1600))).astype(np.float32))
ok('a loud sound after it is not clipped into noise at once', float(np.abs(loud).max()) <= 1.0 and quiet.gain < 15)
ok('a normal voice is left as it is', float(np.abs(hearing.Agc()((0.3 * np.sin(np.linspace(0, 50, 1600))).astype(np.float32))).max()) <= 0.31)
def broken(): raise OSError('no microphone')
hearing._open_mic = broken
try: hearing.listen_mic('ru'); r = False
except OSError: r = 'OSError' in hearing.state()['error']
ok('a missing microphone is raised and noted', r)

hearing._open_mic = lambda: FakeRec(4, 10)
hearing.available = lambda: {'capture': True, 'asr': True}
c, b = post('/listen', {'lang': 'ru-RU'}); r = json.loads(b)
ok('/listen: text for the page', c == 200 and r['text'] == 'привет луна' and r['status'] == 'ready' and not r['cancelled'])
c, b = post('/listen', {'lang': 'de-DE'})
ok('/listen: a language without a model is refused', c == 400 and json.loads(b)['error'] == 'lang')
hearing.available = lambda: {'capture': False, 'asr': True}
c, b = post('/listen', {'lang': 'ru-RU'})
ok('/listen: missing packages are named', c == 501 and json.loads(b)['need'] == ['capture'])
hearing.available = lambda: {'capture': True, 'asr': True}
prepared = []
hearing.prepare = lambda lang='ru': prepared.append(lang)
c, b = post('/listen', {'lang': 'en-US'}); r = json.loads(b)
ok('/listen: another language starts loading its model, nothing recorded', c == 200 and r['status'] == 'loading' and r['text'] == '' and prepared == ['en'])
c, b = post('/listen', {'partial': True})
ok('/listen: partial words', c == 200 and json.loads(b)['text'] == '')
ok('/listen: the microphone level for the test button', set(json.loads(b)['level']) == {'peak', 'gain'})
c, b = post('/listen', {'cancel': True})
ok('/listen: cancel', c == 200 and hearing._cancel.is_set())
c, b = post('/listen', {'lang': 5})
ok('/listen: junk is refused', c == 400)
req = urllib.request.Request('http://127.0.0.1:8802/listen', b'{}', {'Content-Type': 'application/json'})
try: urllib.request.urlopen(req); code = 200
except urllib.error.HTTPError as e: code = e.code
ok('/listen needs the app token', code == 403)
