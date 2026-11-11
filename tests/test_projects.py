import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app, audit, projects
from http.server import ThreadingHTTPServer
tmp = pathlib.Path(tempfile.mkdtemp())
audit.FILE = tmp / 'journal.jsonl'; projects.ROOT = tmp / 'sandbox'; projects.MANIFESTS = tmp / 'manifests'; projects.WS_FILE = tmp / 'ws.json'
__import__('character').MEMORY_FILE = tmp / 'memory.json'; app.load_memory()
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)


def P(name, *files):
    return json.dumps({'project': name, 'files': [{'path': p, 'text': t} for p, t in files]}, ensure_ascii=False)


def code(src):
    try: return projects.propose(src)
    except ValueError as e: return str(e)


GOOD = P('Змейка', ('main.py', 'print("hi")\n'), ('src/game.py', 'class Game:\n    pass\n'), ('README.md', '# Змейка\n'))
ok('bad shapes', all(code(x) == 'bad' for x in ['{', '[]', '{"project":"a"}', '{"project":"a","files":[]}', '{"project":"!!!","files":[{"path":"a.py","text":"x"}]}',
                                                '{"project":"a","files":[{"path":"a.py","text":1}]}', P('a', *[('f%d.py' % i, 'x') for i in range(41)])]))
for bad in ['../x.py', '/etc/x.py', 'C:/x.py', 'a\\b.py', 'a/../../x.py', '.hidden/x.py', 'con.py', 'a/nul.txt', 'x.py.', 'a//b.py', 'x' * 130 + '.py']:
    ok('path refused: ' + bad[:20], code(P('p', (bad, 'x'))) == 'path')
ok('secret file refused', code(P('p', ('.env', 'K=1'))) == 'path' and code(P('p', ('config/password.txt', 'x'))) == 'secret')
ok('programs and launch scripts refused', all(code(P('p', (n, 'x'))) == 'ext' for n in ['run.bat', 'go.ps1', 'a.exe', 'x.vbs', 'lib.dll', 'noext']))
ok('big file refused', code(P('p', ('a.py', 'x' * 120001))) == 'big')
ok('duplicate path refused', code(P('p', ('a.py', 'x'), ('A.py', 'y'))) == 'path')
ok('.gitignore is allowed', isinstance(code(P('p', ('.gitignore', '*.pyc'))), dict))

plate = code(GOOD)
ok('plate lists every file and has a pseudo diff', isinstance(plate, dict) and len(plate['files']) == 3 and plate['file'] == 'Змейка' and '@@ src/game.py (3) @@' in plate['diff'] and '+print("hi")' in plate['diff'])
ok('nothing is created before the press', not (tmp / 'sandbox').exists())

srv = ThreadingHTTPServer(('127.0.0.1', 8797), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d, token=True):
    h = {'Content-Type': 'application/json'}
    if token: h['X-App-Token'] = app.TOKEN
    r = urllib.request.Request('http://127.0.0.1:8797' + path, json.dumps(d).encode(), h)
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
ok('apply needs the token header', post('/project/make', {'token': plate['token']}, False)[0] == 403)
ok('unknown token refused', post('/project/make', {'token': 'nope'})[0] == 403)
c, b = post('/project/make', {'token': plate['token']})
folder = tmp / 'sandbox' / 'Змейка'
ok('created inside the sandbox only', c == 200 and (folder / 'main.py').read_text(encoding='utf-8') == 'print("hi")\n' and (folder / 'src' / 'game.py').is_file() and json.loads(b)['count'] == 3)
ok('single use', post('/project/make', {'token': plate['token']})[0] == 403)
ok('journal has it with an undo', any(e['kind'] == 'project' and e['canUndo'] for e in audit.listing()))
ok('same project again: existing files are never overwritten', code(GOOD) == 'exists')
(folder / 'main.py').write_text('MY OWN\n', encoding='utf-8')
ok('overwrite refused', code(P('Змейка', ('main.py', 'x'))) == 'exists')
more = code(P('Змейка', ('extra.py', 'x = 1\n')))
ok('new files may join an existing project', isinstance(more, dict))
ok('apply adds the file and keeps his', post('/project/make', {'token': more['token']})[0] == 200 and (folder / 'extra.py').is_file() and (folder / 'main.py').read_text(encoding='utf-8') == 'MY OWN\n')

fid = next(e['id'] for e in audit.listing() if e['kind'] == 'project' and e['x'] == 'Змейка' and not e['undone'] and e['canUndo'])
ids = [e['id'] for e in audit.listing() if e['kind'] == 'project']
# the first project's main.py was edited by him -> its undo is refused and nothing is deleted
first = min(ids)
c, b = post('/journal/undo', {'id': first})
ok('undo refused when he changed a file', c == 409 and (folder / 'game.py').exists() is False and (folder / 'src' / 'game.py').is_file() and (folder / 'main.py').is_file())
(folder / 'main.py').write_bytes(b'print("hi")\n')
c, b = post('/journal/undo', {'id': first})
ok('undo removes exactly her files; the later file stays', c == 200 and not (folder / 'main.py').exists() and not (folder / 'src').exists() and (folder / 'extra.py').is_file())
c, b = post('/journal/undo', {'id': max(ids)})
ok('undoing the second project removes the folder when empty', c == 200 and not folder.exists() and (tmp / 'sandbox').is_dir())

# a fresh project in a nested folder, and an undo of a manifest outside the manifests folder
evil = tmp / 'evil.json'; evil.write_text('{"folder": "%s", "files": [], "dirs": []}' % str(tmp).replace('\\', '/'))
import hashlib
bid = audit.log('project', 'x', True, True, path=tmp, b=evil, h=hashlib.sha256(evil.read_bytes()).hexdigest())
ok('manifest outside the manifests folder refused', post('/journal/undo', {'id': bid})[0] == 409)

# a link or junction pointing out of the sandbox cannot be used
outside = tmp / 'outside'; outside.mkdir()
(tmp / 'sandbox').mkdir(exist_ok=True)
link = tmp / 'sandbox' / 'Ссылка'
try:
    os.symlink(outside, link, target_is_directory=True)
    made = True
except OSError:   # no symlink right: a junction needs none
    import subprocess
    made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True).returncode == 0
if made:
    ok('a link out of the sandbox is refused', code(P('Ссылка', ('a.py', 'x'))) in ('path', 'exists') and not (outside / 'a.py').exists())
else:
    print('SKIP symlink test (no rights)')

# server flow with a fake model
mode = {}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    mode['prompt'] = m[0]['content']
    for piece in mode['reply']: yield piece
app.generate_stream = fake
def chat(**kw):
    c, b = post('/chat', dict({'message': 'сделай змейку', 'agent': True, 'work': True}, **kw))
    return c, [json.loads(l) for l in b.splitlines() if l]
spec = P('Тетрис', ('main.py', 'print(1)\n'))
mode['reply'] = ['[happy] Подготовила проект, посмотри. ', '```lunaproject\n' + spec[:30], spec[30:] + '\n```\n', 'Применишь?']
c, ev = chat()
pl = [e['project'] for e in ev if 'project' in e]
ok('project plate event, not shown as code, not spoken', c == 200 and len(pl) == 1 and not any('code' in e for e in ev) and not any('lunaproject' in e.get('answer', '') or '{' in e.get('answer', '') for e in ev))
ok('prompt explains lunaproject', 'lunaproject' in mode['prompt'] and 'Применить' in mode['prompt'])
ok('history keeps the proposal', any('lunaproject' in h['content'] for h in app.HISTORY))
ok('nothing written by the chat itself', not (tmp / 'sandbox' / 'Тетрис').exists())
mode['reply'] = ['Хм ```lunaproject\n' + P('x', ('../a.py', 'x')) + '\n``` ладно']
ok('bad path -> projectfail', any(e.get('projectfail') == 'path' for e in chat()[1]))
mode['reply'] = ['Хм ```lunaproject\n{oops\n``` ладно']
ok('broken JSON -> projectfail bad', any(e.get('projectfail') == 'bad' for e in chat()[1]))
mode['reply'] = ['Хм ```lunaproject\n' + spec + '\n``` ладно']
ok('agent off -> no plate', not any('project' in e for e in chat(agent=False)[1]))
ok('her own initiative -> no plate', not any('project' in e for e in chat(initiative='idle')[1]))

# ---- any folder: only folders the creator added ----
game = tmp / 'work' / 'Game'; (game / 'src').mkdir(parents=True)
(game / 'src' / 'main.py').write_bytes(b'print(1)\n'); (game / 'secret_token.txt').write_text('abc'); (game / '.git').mkdir()
def W(ws, *files): return json.dumps({'workspace': ws, 'files': [{'path': p, 'text': t} for p, t in files]})
ok('no folders by default', projects.workspaces() == [] and projects.workspace_block() == '')
ok('a folder she was not given is refused', code(W('Game', ('a.py', 'x'))) == 'nows')
def addw(path):
    try: return projects.add_workspace(path)
    except ValueError as e: return str(e)
home = pathlib.Path.home()
ok('unsafe folders refused', all(addw(x) == 'unsafe' for x in [str(pathlib.Path(tmp.anchor)), str(home), str(home / 'Documents'), str(pathlib.Path(projects.HERE)), str(pathlib.Path(projects.HERE).parent), 'C:\\Windows\\System32']))
ok('a folder under AppData is refused', addw(str(game)) == 'unsafe')
projects.SYSTEM_DIRS = tuple(x for x in projects.SYSTEM_DIRS if x != 'appdata')   # the test folders live in the temp dir
ok('bad and missing refused', addw('') == 'bad' and addw(None) == 'bad' and addw(str(tmp / 'nope')) == 'notdir')
ok('a good folder is added', addw(str(game)).get('name') == 'Game' and addw(str(game)) == 'dup')
blk = projects.workspace_block()
ok('her prompt block lists the files but not secrets or hidden folders', 'src/main.py' in blk and 'secret' not in blk and '.git' not in blk)
ok('traversal in a folder project refused', code(W('Game', ('../x.py', 'x'))) == 'path' and code(W('Game', ('a.exe', 'x'))) == 'ext')
ok('existing file in a folder is never overwritten', code(W('Game', ('src/main.py', 'x'))) == 'exists')
wp = code(W('Game', ('src/util.py', 'x = 1\n'), ('docs/NOTES.md', '# n\n')))
ok('plate says it is in place', isinstance(wp, dict) and wp['inplace'] and wp['file'] == 'Game')
ok('nothing written before the press', not (game / 'src' / 'util.py').exists())
c, b = post('/project/make', {'token': wp['token']})
ok('files added into the folder, existing untouched', c == 200 and (game / 'src' / 'util.py').is_file() and (game / 'docs' / 'NOTES.md').is_file() and (game / 'src' / 'main.py').read_bytes() == b'print(1)\n')
wid = max(e['id'] for e in audit.listing() if e['kind'] == 'project')
c, b = post('/journal/undo', {'id': wid})
ok('undo removes only her files and the folder she made; the project stays', c == 200 and not (game / 'src' / 'util.py').exists() and not (game / 'docs').exists() and (game / 'src' / 'main.py').is_file() and game.is_dir())
wp = code(W('Game', ('late.py', 'x')))
projects.remove_workspace('Game')
ok('folder taken away before the press: nothing is written', post('/project/make', {'token': wp['token']})[0] == 409 and not (game / 'late.py').exists())
projects.add_workspace(str(game))
wp = code(W('Game', ('keep.py', 'x')))
post('/project/make', {'token': wp['token']})
kid = max(e['id'] for e in audit.listing() if e['kind'] == 'project')
projects.remove_workspace('Game')
ok('undo is refused when the folder is no longer allowed', post('/journal/undo', {'id': kid})[0] == 409 and (game / 'keep.py').exists())
projects.add_workspace(str(game))
ok('undo works again once allowed', post('/journal/undo', {'id': kid})[0] == 200 and not (game / 'keep.py').exists())

# the settings endpoint
ok('ws endpoint needs the token', post('/project/ws', {'op': 'list'}, False)[0] == 403)
c, b = post('/project/ws', {'op': 'list'})
ok('list', c == 200 and [w['name'] for w in json.loads(b)['items']] == ['Game'])
c, b = post('/project/ws', {'op': 'add', 'path': str(tmp / 'nope')})
ok('add a missing folder -> error', c == 400 and json.loads(b)['error'] == 'project:notdir')
c, b = post('/project/ws', {'op': 'add', 'path': str(pathlib.Path.home())})
ok('add home -> unsafe', c == 400 and json.loads(b)['error'] == 'project:unsafe')
c, b = post('/project/ws', {'op': 'remove', 'name': 'Game'})
ok('remove', c == 200 and json.loads(b)['items'] == [])
ok('bad op', post('/project/ws', {'op': 'zap'})[0] == 400)
ok('folder changes are in the journal', any(e['kind'] == 'wsdel' for e in audit.listing()))
# her prompt mentions folders only when some are allowed
projects.add_workspace(str(game))
mode['reply'] = ['Ок']
chat()
ok('prompt shows the allowed folder and the workspace field', 'workspace' in mode['prompt'] and 'src/main.py' in mode['prompt'])
projects.remove_workspace('Game')
chat()
ok('prompt has no folder block when none allowed', 'НОВЫЕ файлы' not in mode['prompt'])
print('end')
