import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app, audit, codeedit, devtools
from http.server import ThreadingHTTPServer
tmp = pathlib.Path(tempfile.mkdtemp())
audit.FILE = tmp / 'journal.jsonl'; codeedit.BACKUPS = tmp / 'bk'
__import__('character').MEMORY_FILE = tmp / 'memory.json'; app.load_memory()
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

proj = tmp / 'proj'; proj.mkdir()
crlf = proj / 'Player.cs'
SRC = 'class Player {\r\n    int hp = 10;\r\n    void Hit() { hp -= 1; }\r\n    void Heal() { hp += 1; }\r\n}\r\n'
crlf.write_bytes(b'\xef\xbb\xbf' + SRC.encode('utf-8'))
(proj / 'secret_token.txt').write_text('abc')
(proj / 'dup.py').write_text('x = 1\nx = 1\n')
(proj / 'bin.py').write_bytes(b'\xff\xfe\x00bad')

def show(path, label=None):
    """The creator agreed to show her this file (the real read path)."""
    tok = 'tk' + str(time.time())
    devtools.FOUND[tok] = {'path': str(path), 'label': label or path.name, 't': time.time()}
    return devtools.read_code(tok)

def E(file, *pairs):
    return json.dumps({'file': file, 'edits': [{'find': a, 'replace': b} for a, b in pairs]}, ensure_ascii=False)

def code(src):
    try: return codeedit.propose(src)
    except ValueError as e: return str(e)

ok('file she was not shown is refused', code(E('Player.cs', ('hp = 10', 'hp = 20'))) == 'nofile')
show(crlf); show(proj / 'dup.py'); show(proj / 'bin.py')
ok('secret-named file cannot even be shown', (lambda: (devtools.FOUND.update(z={'path': str(proj / 'secret_token.txt'), 'label': 'secret_token.txt', 't': time.time()}), devtools.read_code('z')))) and True
try: devtools.read_code('z'); r = False
except OSError: r = True
ok('secret-named file refused', r and code(E('secret_token.txt', ('abc', 'x'))) == 'nofile')
ok('bad shapes', all(code(x) == 'bad' for x in ['{', '[]', '{"file":"Player.cs"}', '{"file":"Player.cs","edits":[]}', '{"file":"Player.cs","edits":[{"find":"","replace":"x"}]}', '{"file":"Player.cs","edits":[{"find":"a","replace":1}]}', json.dumps({'file': 'Player.cs', 'edits': [{'find': 'a', 'replace': 'b'}] * 13})]))
ok('no match', code(E('Player.cs', ('hp = 99', 'x'))) == 'nomatch')
ok('ambiguous match refused', code(E('dup.py', ('x = 1', 'x = 2'))) == 'multi')
ok('no-op refused', code(E('Player.cs', ('hp = 10', 'hp = 10'))) == 'same')
ok('non-utf8 refused', code(E('bin.py', ('bad', 'x'))) in ('encoding', 'nomatch') and code(E('bin.py', ('bad', 'x'))) == 'encoding')

plate = code(E('Player.cs', ('int hp = 10;', 'int hp = 20;'), ('hp -= 1;', 'hp -= 2;')))
ok('plate has a diff', isinstance(plate, dict) and plate['added'] == 2 and plate['removed'] == 2 and '+    int hp = 20;' in plate['diff'])
ok('nothing changed before the press', crlf.read_bytes() == b'\xef\xbb\xbf' + SRC.encode())

srv = ThreadingHTTPServer(('127.0.0.1', 8796), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d, token=True):
    h = {'Content-Type': 'application/json'}
    if token: h['X-App-Token'] = app.TOKEN
    r = urllib.request.Request('http://127.0.0.1:8796' + path, json.dumps(d).encode(), h)
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
ok('apply needs the token header', post('/code/edit', {'token': plate['token']}, False)[0] == 403)
c, b = post('/code/edit', {'token': plate['token']})
raw = crlf.read_bytes()
ok('applied; BOM and CRLF kept', c == 200 and raw.startswith(b'\xef\xbb\xbf') and raw.count(b'\r\n') == 5 and b'hp = 20' in raw and b'hp -= 2' in raw and b'\n' not in raw.replace(b'\r\n', b''))
ok('replay refused', post('/code/edit', {'token': plate['token']})[0] == 403)
bk = list((tmp / 'bk').iterdir())
ok('backup of the original', len(bk) == 1 and bk[0].read_bytes() == b'\xef\xbb\xbf' + SRC.encode())
e = audit.listing()[0]
ok('journaled and undoable, no path leaked', e['kind'] == 'edit' and e['canUndo'] and 'p' not in e and 'b' not in e and 'h' not in e)
c, b = post('/journal/undo', {'id': e['id']})
ok('undo restores the original bytes', c == 200 and crlf.read_bytes() == b'\xef\xbb\xbf' + SRC.encode())

# the file changed behind her back
p2 = code(E('Player.cs', ('hp += 1;', 'hp += 5;')))
crlf.write_bytes(crlf.read_bytes() + b'// me\r\n')
ok('stale proposal refused (409 changed)', post('/code/edit', {'token': p2['token']}) == (409, '{"error": "edit:changed"}'))
# undo refuses to destroy newer work
p3 = code(E('Player.cs', ('hp += 1;', 'hp += 6;')))
post('/code/edit', {'token': p3['token']})
e = audit.listing()[0]
crlf.write_bytes(crlf.read_bytes() + b'// later work\r\n')
c, b = post('/journal/undo', {'id': e['id']})
ok('undo refused when the file changed since', c == 409 and b'changed' in b.encode() and b'later work' in crlf.read_bytes())
# forged journal entry cannot restore from outside the backups folder
evil = tmp / 'evil.txt'; evil.write_text('EVIL')
target = tmp / 'victim.txt'; target.write_text('v')
import hashlib
fid = audit.log('edit', 'victim.txt', True, True, path=target, b=evil, h=hashlib.sha256(b'v').hexdigest())
ok('backup outside the backups folder refused', post('/journal/undo', {'id': fid})[0] == 409 and target.read_text() == 'v')

# server flow with a fake model
mode = {}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    mode['prompt'] = m[0]['content']
    for piece in mode['reply']: yield piece
app.generate_stream = fake
def chat(**kw):
    c, b = post('/chat', dict({'message': 'поправь Heal', 'agent': True, 'work': True}, **kw))
    return c, [json.loads(l) for l in b.splitlines() if l]
crlf.write_bytes(bytes([0xef,0xbb,0xbf]) + SRC.encode()); show(crlf)
spec = E('Player.cs', ('void Heal() { hp += 1; }', 'void Heal() { hp = Math.Min(hp + 1, 10); }'))
mode['reply'] = ['[happy] Подготовила правку, посмотри. ', '```lunaedit\n' + spec[:30], spec[30:] + '\n```\n', 'Применишь?']
c, ev = chat()
pl = [e['edit'] for e in ev if 'edit' in e]
print([ (k, str(v)[:80]) for e in ev for k, v in e.items()]); ok('edit plate event, not shown as code, not spoken', c == 200 and len(pl) == 1 and not any('code' in e for e in ev) and not any('lunaedit' in e.get('answer', '') or '{' in e.get('answer', '') for e in ev))
ok('prompt explains lunaedit', 'lunaedit' in mode['prompt'] and 'Применить' in mode['prompt'])
ok('history keeps the proposal', any('lunaedit' in h['content'] for h in app.HISTORY))
mode['reply'] = ['Хм ```lunaedit\n' + E('Player.cs', ('нет такого', 'x')) + '\n``` ладно']
c, ev = chat()
ok('mismatch -> editfail nomatch', any(e.get('editfail') == 'nomatch' for e in ev))
mode['reply'] = ['Хм ```lunaedit\n{oops\n``` ладно']
ok('broken JSON -> editfail bad', any(e.get('editfail') == 'bad' for e in chat()[1]))
mode['reply'] = ['Хм ```lunaedit\n' + spec + '\n``` ладно']
ok('agent off -> no plate', not any('edit' in e for e in chat(agent=False)[1]))
ok('her own initiative -> no plate', not any('edit' in e for e in chat(initiative='idle')[1]))
print('end')
