import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error, ast
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app, unreal_bridge as ub
from http.server import ThreadingHTTPServer

# parsing: valid and hostile
good = ['spawn cube', 'spawn sphere 0 0 200 2', 'spawn pointlight 10,5 -20 300', 'move 0 0 50', 'rotate 0 90 0', 'scale 2', 'delete', 'SPAWN Cone']
bad = ['spawn', 'spawn cube 1 2', 'spawn tree', 'spawn cube 1 2 3 4 5', 'move 1 2', 'move a b c', 'move 9999999999 0 0', 'scale 0', 'scale 1000',
       'delete all', 'exec import os', '__import__("os")', 'spawn cube 0 0 __import__', 'rotate 0 0 361', 'move 1e9 0 0', 'spawn cube; 0 0 0', '']
for g in good:
    o = ub.parse(g); compile(ub.render(o), 'snippet', 'exec')
print('good ok:', len(good))
for b in bad:
    try: ub.parse(b); print('ACCEPTED', repr(b))
    except ValueError: pass
print('bad rejected:', len(bad))
print(ub.describe(ub.parse('spawn cube')), '|', ub.describe(ub.parse('move 1 2 3')), '|', ub.describe(ub.parse('delete')))
print(ub.render(ub.parse('rotate 0 90 0'))[-420:])

# run with a fake editor
sent = []
def fake_ok(code):
    sent.append(code)
    return {'success': True, 'result': 'None', 'output': [{'type': 'Info', 'output': 'LUNA_RESULT:{"done": "spawn", "name": "Luna_cube"}\n'}]}
print('run ok:', ub.run(ub.parse('spawn cube'), fake_ok))
print('nothing selected:', ub.run(ub.parse('move 0 0 1'), lambda c: {'success': True, 'output': [{'output': 'LUNA_RESULT:{"error": "nothing_selected"}'}]}))
def noed(c): raise RuntimeError('noeditor')
print('no editor:', ub.run(ub.parse('delete'), noed))
print('script error:', ub.run(ub.parse('delete'), lambda c: {'success': False, 'result': 'Traceback', 'output': []}))
ub._recent[:] = []
for i in range(ub.MAX_PER_MINUTE): ub.run(ub.parse('scale 2'), fake_ok)
print('rate:', ub.run(ub.parse('scale 2'), fake_ok))
ub._recent[:] = []

# server flow
__import__('character').MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'
app.KEY = 'dummy'; app.load_memory()
prompts = []
def fake(m, model=None, **kw):
    prompts.append(m[0]['content'])
    yield 'Сейчас сделаю. [ue:spawn cube 0 0 100] [ue:delete] [ue:run os.system] [ue:spawn tree]'
app.generate_stream = fake
ub._transport = fake_ok
srv = ThreadingHTTPServer(('127.0.0.1', 8784), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d):
    r = urllib.request.Request('http://127.0.0.1:8784' + path, json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
st, body = post('/chat', {'message': 'сделай куб', 'agent': True, 'work': True, 'unreal': False})
print('switch off -> unreal event:', 'unreal' in body, '| prompt mentions ue:', '[ue:' in prompts[-1])
st, body = post('/chat', {'message': 'сделай куб', 'agent': True, 'work': True, 'unreal': True})
ev = [json.loads(l) for l in body.splitlines() if l]
plates = [e['unreal'] for e in ev if 'unreal' in e]
print('plates:', [(p['text'], p['risky']) for p in plates], '| prompt has ue:', '[ue:' in prompts[-1])
print('spoken has no tags:', [e['answer'] for e in ev if 'answer' in e])
n = len(sent)
print('bad token:', post('/unreal/run', {'token': 'x'})[0], '| nothing ran:', len(sent) == n)
st, b = post('/chat', {'message': 'x', 'agent': True, 'work': True, 'unreal': True, 'initiative': 'idle'})
print('initiative gets no plates:', 'unreal' not in b)
print('run:', post('/unreal/run', {'token': plates[0]['token']}))
print('replay:', post('/unreal/run', {'token': plates[0]['token']})[0])
print('snippet sent contains pos:', '[0.0, 0.0, 100.0]' in sent[-1])
