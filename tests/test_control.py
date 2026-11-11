import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
from luna.hands import control, inputctl
from http.server import ThreadingHTTPServer
inputctl.DRY = True
import traceback
_o = control.plan_step
def _w(*a, **k):
    try: return _o(*a, **k)
    except BaseException: traceback.print_exc(); raise
control.plan_step = _w
__import__('luna.core.character', fromlist=['_']).MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'
app.KEY = 'dummy'; app.load_memory()
replies = []
def fake(m, model=None, **kw):
    if isinstance(m[-1]['content'], list):   # a screenshot step
        yield replies.pop(0)
    elif 'запиши' in m[-1]['content']:
        yield 'Хорошо, сейчас сделаю. [do:открой Блокнот и напиши привет]'
    else:
        yield 'Привет.'
app.generate_stream = fake
srv = ThreadingHTTPServer(('127.0.0.1', 8783), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d):
    r = urllib.request.Request('http://127.0.0.1:8783' + path, json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
IMG = 'data:image/jpeg;base64,AAAA'
print('no session step:', post('/agent/step', {'image': IMG, 'steps': []})[0])
print('no session do:', post('/agent/do', {'action': {'action': 'click', 'x': 5, 'y': 5}})[0])
st, body = post('/chat', {'message': 'запиши', 'agent': True, 'control': False})
print('control off -> task event:', 'task' in body)
st, body = post('/chat', {'message': 'запиши', 'agent': True, 'control': True})
ev = [json.loads(l) for l in body.splitlines() if l]
task = [e for e in ev if 'task' in e][0]['task']; print('task:', task['text'])
print('bad token start:', post('/agent/start', {'token': 'x'})[0])
print('start:', post('/agent/start', {'token': task['token']})[0])
print('start replay:', post('/agent/start', {'token': task['token']})[0])
replies += ['{"thought":"Кликаю по полю","action":"click","x":500,"y":400,"risky":false}',
            'Вот: {"thought":"Печатаю","action":"type","text":"привет","risky":false}',
            '{"thought":"хак","action":"key","key":"win+r"}',
            '{"thought":"удаляю","action":"key","key":"delete"}',
            'не json вообще']
for i in range(3):
    st, b = post('/agent/step', {'image': IMG, 'steps': ['a'], 'lang': 'ru'})
    print('step', i, st, b[:140])
    if st == 200:
        act = json.loads(b)['action']
        print('  do:', post('/agent/do', {'action': act}))
print('garbage action do:', post('/agent/do', {'action': {'action': 'key', 'key': 'win+r'}}))
print('exec action do:', post('/agent/do', {'action': {'action': 'run', 'cmd': 'calc'}}))
control.SESSION['on'] = True; control.SESSION['until'] = 9e18; control.SESSION['pos'] = (0, 0)
x, y = inputctl.cursor()
print('moved guard:', post('/agent/do', {'action': {'action': 'click', 'x': 5, 'y': 5}}), 'cursor', (x, y), 'session on:', control.SESSION['on'])
control.SESSION.update(on=True, until=9e18, acts=control.MAX_ACTS, pos=None)
print('budget:', post('/agent/do', {'action': {'action': 'wait'}}))
print('stop:', post('/agent/stop', {}))
