import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
from luna.hands import office
from luna.core import audit, providers
from luna.dev import unreal_bridge
from http.server import ThreadingHTTPServer
tmp = pathlib.Path(tempfile.mkdtemp())
office.FOLDER = tmp / 'Luna'; audit.FILE = tmp / 'journal.jsonl'
providers.KEYS_FILE = tmp / 'keys.dat'; providers.CHOICE_FILE = tmp / 'providers.json'
__import__('luna.core.character', fromlist=['_']).MEMORY_FILE = tmp / 'memory.json'; app.load_memory()
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
codes = []
def fake_transport(code, wait=4.0):
    codes.append(code)
    out = 'LUNA_RESULT:{"done":"undo","count":1}' if 'TRANSACTION UNDO' in code else 'LUNA_RESULT:{"done":"spawn","name":"Luna_cube"}'
    return {'success': True, 'output': [{'output': out}]}
unreal_bridge._transport = fake_transport
srv = ThreadingHTTPServer(('127.0.0.1', 8795), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d, token=True):
    h = {'Content-Type': 'application/json'}
    if token: h['X-App-Token'] = app.TOKEN
    r = urllib.request.Request('http://127.0.0.1:8795' + path, json.dumps(d).encode(), h)
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read().decode() or '{}')
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read().decode() or '{}')
J = lambda: post('/journal/list', {})[1]['entries']

ok('empty journal', J() == [])
ok('journal needs the token', post('/journal/list', {}, False)[0] == 403)

# a document: create through the real endpoints, then take it back
SPEC = {'type': 'docx', 'title': 'Письмо', 'blocks': [{'p': 'Привет'}]}
plate = office.propose(json.dumps(SPEC)); c, r = post('/doc/make', {'token': plate['token']})
f = office.FOLDER / r['name']
e = J()[0]
ok('doc logged, undo offered', f.is_file() and e['kind'] == 'doc' and e['canUndo'] and e['x'] == r['name'])
c, r2 = post('/journal/undo', {'id': e['id']})
ok('undo moves the file to the Recycle Bin', c == 200 and not f.exists())
l = J()
ok('entry marked undone + an "undo" entry written', next(x for x in l if x['id'] == e['id'])['undone'] and l[0]['kind'] == 'undo')
ok('second undo refused', post('/journal/undo', {'id': e['id']}) == (409, {'error': 'journal:cannot'}))

# a forged entry pointing outside her folder is refused
outside = tmp / 'precious.txt'; outside.write_text('x')
fid = audit.log('doc', 'precious.txt', True, True, path=outside)
ok('undo never touches files outside her folder', post('/journal/undo', {'id': fid})[0] == 409 and outside.exists())

# opening something cannot be undone
oid = audit.log('open', 'Google')
ok('"open" has no undo', not next(x for x in J() if x['id'] == oid)['canUndo'] and post('/journal/undo', {'id': oid})[0] == 409)
ok('bad ids rejected', post('/journal/undo', {'id': 'x'})[0] == 400 and post('/journal/undo', {'id': True})[0] == 400 and post('/journal/undo', {'id': 999})[0] == 409)

# Unreal: only the latest step can be undone; the undo snippet is fixed and she cannot ask for it
for text in ('spawn cube', 'spawn sphere'):
    o = unreal_bridge.parse(text); t = unreal_bridge.propose(text)['token']; post('/unreal/run', {'token': t})
ue = [x for x in J() if x['kind'] == 'unreal']
ok('two unreal steps logged, only the newest can be undone', len(ue) == 2 and ue[0]['canUndo'] and not ue[1]['canUndo'])
ok('older step refused', post('/journal/undo', {'id': ue[1]['id']})[0] == 409)
c, r = post('/journal/undo', {'id': ue[0]['id']})
ok('newest undone via the editor transaction', c == 200 and 'TRANSACTION UNDO' in codes[-1])
ue = [x for x in J() if x['kind'] == 'unreal']
ok('then the previous one becomes undoable', ue[1]['canUndo'] is True)
ok('she cannot request an undo herself', unreal_bridge.propose('undo') is None)

# keys never reach the journal; recent actions reach her prompt
SECRET = 'sk-NEVER-IN-JOURNAL-123456'
audit.log('key.set', 'OpenAI')
ok('no secret in the journal file', SECRET not in audit.FILE.read_text(encoding='utf-8'))
app.AGENT = True
p = app.system_prompt('что ты делала?')
ok('prompt tells her what she really did', 'Что ты на самом деле делала руками' in p and 'сохранила ключ для OpenAI' in p)
audit.FILE.write_text('', encoding='utf-8')
ok('empty journal -> no such line', 'Что ты на самом деле делала руками' not in app.system_prompt('привет'))

# trimming and clear
for i in range(audit.KEEP + 30): audit.log('open', 'x%d' % i)
ok('journal trimmed to KEEP', len(audit._read()) == audit.KEEP)
ok('clear', post('/journal/clear', {})[0] == 200 and J() == [])
