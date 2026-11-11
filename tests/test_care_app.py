"""Care on her own initiative through the real server: the greeting carries the caring hint, her prompt shows dates and promises."""
import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app, audit, character
from http.server import ThreadingHTTPServer
tmp = pathlib.Path(tempfile.mkdtemp())
audit.FILE = tmp / 'journal.jsonl'
character.MEMORY_FILE = tmp / 'memory.json'; app.load_memory()
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

srv = ThreadingHTTPServer(('127.0.0.1', 8797), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d):
    r = urllib.request.Request('http://127.0.0.1:8797' + path, json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()

seen = {}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    seen['system'], seen['last'] = m[0]['content'], m[-1]['content']
    yield '[happy] Привет!'
app.generate_stream = fake
now = time.time()
M = character.MEMORY
M['moments'] = [{'kind': 'date', 'text': 'Экзамен по математике', 'due': character.day_start(now), 't': now - 86400, 'cared': 0.0, 'n': 0}]

c, _ = post('/chat', {'initiative': 'greet'})
ok('greeting carries the care hint about today\'s exam', c == 200 and 'Экзамен по математике' in seen['last'] and seen['last'].startswith(character.NOTE))
ok('her prompt lists the date as today', '[дата, сегодня] Экзамен' in seen['system'])
c, _ = post('/chat', {'initiative': 'greet'})
ok('a second greeting right away does not repeat it', 'Экзамен' not in seen['last'])
ok('nothing to care about: the plain greeting, no stray text', 'фразы.  ' not in seen['last'] and 'фразы. [' in seen['last'])
c, _ = post('/chat', {'initiative': 'idle'})
ok('idle initiative gets no care hint', 'Экзамен' not in seen['last'])

M['moments'] = []; M['late'] = 0
real = character.time
class Night:
    def __getattr__(self, n): return getattr(real, n)
    def localtime(self, t=None):
        lt = real.localtime(t)
        return real.struct_time((lt.tm_year, lt.tm_mon, lt.tm_mday, 3) + tuple(lt)[4:]) if t is None else lt
character.time = Night()
post('/chat', {'initiative': 'idle'})
ok('her own initiative at night does not count as the creator being up', M['late'] == 0)
post('/chat', {'message': 'не могу уснуть'})
ok('a message from the creator at night is noted', M['late'] > 0)
character.time = real

# scheduled waking: the page asks /care/due, then speaks with initiative 'care'
class Day:   # a fixed hour so the test does not depend on when it runs
    def __init__(self, hour): self.hour = hour
    def __getattr__(self, n): return getattr(real, n)
    def localtime(self, t=None):
        lt = real.localtime(t)
        return real.struct_time((lt.tm_year, lt.tm_mon, lt.tm_mday, self.hour) + tuple(lt)[4:]) if t is None else lt
M['moments'] = [{'kind': 'date', 'text': 'Сдать отчёт', 'due': character.day_start(now) + 86400, 't': now - 86400, 'cared': 0.0, 'n': 0}]
character.time = Day(14)
c, b = post('/care/due', {})
ok('midday, deadline tomorrow: it is time', c == 200 and json.loads(b) == {'due': True})
ok('/care/due only looks: asking twice changes nothing', json.loads(post('/care/due', {})[1])['due'] is True and M['moments'][0]['n'] == 0)
c, b = post('/chat', {'initiative': 'care'})
ok('care initiative carries the date', c == 200 and 'Сдать отчёт' in seen['last'] and M['moments'][0]['n'] == 1)
ok('afterwards it is not due again', json.loads(post('/care/due', {})[1])['due'] is False)
c, b = post('/chat', {'initiative': 'care'})
ok('care with nothing to say is refused, not an empty message', c == 400)
M['moments'][0].update(cared=0.0, n=0)
character.time = Day(3)
ok('never wakes her at night', json.loads(post('/care/due', {})[1])['due'] is False)
character.time = Day(22)
ok('...nor late evening', json.loads(post('/care/due', {})[1])['due'] is False)
character.time = Day(14)
M['moments'][0]['due'] = 0
M['moments'][0]['kind'] = 'promise'
ok('an undated promise does not wake her (only greets)', json.loads(post('/care/due', {})[1])['due'] is False)
c, b = post('/care/due', {}) ; ok('endpoint needs the token (POST only, checked by the server)', c == 200)
r = urllib.request.Request('http://127.0.0.1:8797/care/due', b'{}', {'Content-Type': 'application/json'})
try: urllib.request.urlopen(r); code = 200
except urllib.error.HTTPError as e: code = e.code
ok('without the token: 403', code == 403)
character.time = real
