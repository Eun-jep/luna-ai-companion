"""Work mode: code, commands, projects, engines and documents exist for her only while the switch is on; everyday talk stays light."""
import os
import sys, tempfile, pathlib, json, threading, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app, urllib.error
from luna.core import character
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
character.MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'; app.load_memory()

seen = {}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    seen['prompt'] = m[0]['content']
    yield '[happy] Ок. [read:Player.cs]\n```lunadoc\n{"type":"docx","title":"x","blocks":[]}\n```\n'
app.generate_stream = fake
app.generate = lambda m: 'нет'
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8915), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def chat(**kw):
    r = urllib.request.Request('http://127.0.0.1:8915/chat', json.dumps(dict({'message': 'посмотри мой код в Unity и сделай документ'}, **kw)).encode(),
                               {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    with urllib.request.urlopen(r) as x:
        return [json.loads(l) for l in x.read().decode().splitlines() if l.strip()]

ev = chat(agent=True)
p = seen['prompt']
ok('off: no code-work in the prompt', '[run:' not in p and 'lunaedit' not in p and 'lunaproject' not in p and '[doc:' not in p and '[move:' not in p)
ok('off: no read command and no developer guide', '[read:имя файла]' not in p and 'разработчица' not in p)
ok('off: she is told how to get it', 'Рабочий режим' in p)
ok('off: the everyday hands stay', '[find:' in p and '[go:' in p)
ok('off: her read and document requests become nothing', not any(k in e for e in ev for k in ('readfile', 'document', 'docfail', 'notfound', 'choices')))

ev = chat(agent=True, work=True)
p = seen['prompt']
ok('on: the work commands are taught', '[run:' in p and 'lunaedit' in p and 'lunaproject' in p and '[doc:' in p and '[read:имя файла]' in p)
ok('on: the developer guide comes with code talk', 'разработчица' in p)
ok('on: her requests work again', any('readfile' in e or 'notfound' in e for e in ev) and any('document' in e or 'docfail' in e for e in ev))

ev = chat(work=True)
ok('work needs hands (agent) on', '[run:' not in seen['prompt'])

# ---- Godot through the chat ----
from luna.dev import godot_bridge, devtools
gtmp = pathlib.Path(tempfile.mkdtemp()) / 'g'; (gtmp / 'scripts').mkdir(parents=True)
(gtmp / 'project.godot').write_text('config/name="Demo"\nconfig/features=PackedStringArray("4.2")\n', encoding='utf-8')
(gtmp / 'scripts' / 'a.gd').write_text('extends Node\n', encoding='utf-8')
devtools.GRANTED['a.gd'] = {'path': str(gtmp / 'scripts' / 'a.gd'), 't': 9e18}
devtools._state.update(t=9e18, engines=[])
def fake_gd(m, model=None, vision=False, max_tokens=800, **kw):
    seen['prompt'] = m[0]['content']
    yield '[happy] Сейчас. [gd:scene Main 2d]'
app.generate_stream = fake_gd
ev = chat(agent=True, work=True)
plates = [e['godot'] for e in ev if 'godot' in e]
ok('on: a Godot request becomes a plate', len(plates) == 1 and plates[0]['project'] == 'Demo' and 'new scene Main' in plates[0]['text'])
ok('on: the prompt teaches [gd:', '[gd:операция]' in seen['prompt'])
def post(path, d):
    r = urllib.request.Request('http://127.0.0.1:8915' + path, json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
c, b = post('/godot/run', {'token': plates[0]['token']})
ok('the press runs it: no engine here, said plainly', c == 200 and b == {'ok': False, 'error': 'noengine'})
c, b = post('/godot/run', {'token': plates[0]['token']})
ok('the press works once', c == 403)
ev = chat(agent=True)
ok('off: a Godot request does nothing', not any('godot' in e or 'godotfail' in e for e in ev) and '[gd:операция]' not in seen['prompt'])
devtools.GRANTED.clear(); devtools._state.update(projects=[])
ev = chat(agent=True, work=True)
ok('no project: the page is told', any(e.get('godotfail') == 'noproject' for e in ev))

# ---- Unity through the chat ----
from luna.dev import unity_bridge
utmp = pathlib.Path(tempfile.mkdtemp()) / 'u'; (utmp / 'Assets').mkdir(parents=True); (utmp / 'ProjectSettings').mkdir()
(utmp / 'ProjectSettings' / 'ProjectVersion.txt').write_text('m_EditorVersion: 2022.3.10f1\n', encoding='utf-8')
(utmp / 'Assets' / 'P.cs').write_text('using UnityEngine;\n', encoding='utf-8')
devtools.GRANTED['p.cs'] = {'path': str(utmp / 'Assets' / 'P.cs'), 't': 9e19}
def fake_un(m, model=None, vision=False, max_tokens=800, **kw):
    seen['prompt'] = m[0]['content']
    yield '[happy] Сейчас. [unity:scene Main 3d]'
app.generate_stream = fake_un
ev = chat(agent=True, work=True)
plates = [e['unity'] for e in ev if 'unity' in e]
ok('unity on: a request becomes a plate', len(plates) == 1 and plates[0]['project'] == 'u' and 'new 3D scene Main' in plates[0]['text'])
ok('unity on: the prompt teaches [unity:', '[unity:операция]' in seen['prompt'])
c, b = post('/unity/run', {'token': plates[0]['token']})
ok('unity: the press runs it (no Unity here, said plainly)', c == 200 and b == {'ok': False, 'error': 'noengine'})
c, b = post('/unity/run', {'token': plates[0]['token']})
ok('unity: the press works once', c == 403)
ev = chat(agent=True)
ok('unity off: nothing happens', not any('unity' in e or 'unityfail' in e for e in ev) and '[unity:операция]' not in seen['prompt'])

# ---- the project audit through the chat ----
import time as _t
from luna.dev import codescan
sroot = pathlib.Path(tempfile.mkdtemp()) / 'proj'; (sroot / 'src').mkdir(parents=True); (sroot / 'requirements.txt').write_text('flask\n', encoding='utf-8')
(sroot / 'src' / 'a.py').write_text('x = 1\n', encoding='utf-8')
devtools.GRANTED['a.py'] = {'path': str(sroot / 'src' / 'a.py'), 't': 9e19 + 1e19}
def fake_scan(m, model=None, vision=False, max_tokens=800, **kw):
    seen['prompt'] = m[0]['content']
    yield '[happy] Проверю. [scan:проект]'
app.generate_stream = fake_scan
ev = chat(agent=True, work=True)
sp = [e['scan'] for e in ev if 'scan' in e]
ok('scan on: a request becomes a plate', len(sp) == 1 and sp[0]['project'] == 'proj' and '[scan:проект]' in seen['prompt'])
c, b = post('/code/scan', {'token': sp[0]['token']})
ok('scan: the press returns the program report', c == 200 and 'АУДИТ ПРОЕКТА «proj»' in b['text'] and 'requirements.txt: 1 пакетов' in b['text'])
c, b = post('/code/scan', {'token': sp[0]['token']})
ok('scan: the press works once', c == 403)
ev = chat(agent=True)
ok('scan off: nothing happens', not any('scan' in e or 'scanfail' in e for e in ev) and '[scan:проект]' not in seen['prompt'])

# ---- the git review through the chat ----
import shutil as _sh
from luna.dev import gitdiff
if _sh.which('git'):
    import subprocess as _sp
    grepo = pathlib.Path(tempfile.mkdtemp()) / 'gr'; grepo.mkdir()
    def _g(*a): return _sp.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false'] + list(a), cwd=grepo, capture_output=True)
    _g('init', '-q'); (grepo / 'a.py').write_text('x = 1\n'); _g('add', '.'); _g('commit', '-q', '-m', 'b')
    (grepo / 'a.py').write_text('x = 1\nimport pdb\n')
    devtools.GRANTED['a.py'] = {'path': str(grepo / 'a.py'), 't': 9e23}
    def fake_diff(m, model=None, vision=False, max_tokens=800, **kw):
        seen['prompt'] = m[0]['content']
        yield '[happy] Гляну. [diff:working]'
    app.generate_stream = fake_diff
    ev = chat(agent=True, work=True)
    dp = [e['diff'] for e in ev if 'diff' in e]
    ok('diff on: a request becomes a plate', len(dp) == 1 and dp[0]['project'] == 'gr' and '[diff:что]' in seen['prompt'])
    c, b = post('/git/diff', {'token': dp[0]['token']})
    ok('diff: the press returns the program review', c == 200 and 'РАЗБОР ИЗМЕНЕНИЙ' in b['text'] and 'забытая отладка' in b['text'])
    c, b = post('/git/diff', {'token': dp[0]['token']})
    ok('diff: the press works once', c == 403)
    ev = chat(agent=True)
    ok('diff off: nothing happens', not any('diff' in e or 'difffail' in e for e in ev) and '[diff:что]' not in seen['prompt'])

# ---- a read-only query on the project's SQLite file through the chat ----
import sqlite3
from luna.dev import sqlrun
sqroot = pathlib.Path(tempfile.mkdtemp()) / 'sq'; sqroot.mkdir()
_c = sqlite3.connect(sqroot / 'app.db'); _c.execute('create table t (a)'); _c.execute('insert into t values (7)'); _c.commit(); _c.close()
(sqroot / 'main.py').write_text('print(1)\n')
devtools.GRANTED['main.py'] = {'path': str(sqroot / 'main.py'), 't': 9e24}
def fake_sql(m, model=None, vision=False, max_tokens=800, **kw):
    seen['prompt'] = m[0]['content']
    yield '[happy] Гляну. [sql:select a from t]'
app.generate_stream = fake_sql
ev = chat(agent=True, work=True)
qp = [e['sql'] for e in ev if 'sql' in e]
ok('sql on: a request becomes a plate with the exact query', len(qp) == 1 and qp[0]['db'] == 'app.db' and qp[0]['sql'] == 'select a from t' and '[sql:запрос]' in seen['prompt'])
c, b = post('/sql/run', {'token': qp[0]['token']})
ok('sql: the press returns the rows', c == 200 and b['text'] == 'a\n7')
c, b = post('/sql/run', {'token': qp[0]['token']})
ok('sql: the press works once', c == 403)
ev = chat(agent=True)
ok('sql off (no work mode): nothing happens', not any('sql' in e or 'sqlfail' in e for e in ev) and '[sql:запрос]' not in seen['prompt'])
def fake_sql_bad(m, model=None, vision=False, max_tokens=800, **kw):
    yield '[happy] Проверю. [sql:delete from t]'
app.generate_stream = fake_sql_bad
ev = chat(agent=True, work=True)
ok('sql: a write request is refused, no plate', not any('sql' in e for e in ev) and any(e.get('sqlfail', {}).get('fail') == 'notread' for e in ev))

# ---- stack traces next to the message ----
TRACE = 'Traceback (most recent call last):\n  File "C:\\w\\app\\pricing.py", line 7, in price\n    return d["cost"]\nKeyError: \'cost\'\n'
def fake_tr(m, model=None, vision=False, max_tokens=800, **kw):
    seen['last'] = m[-1]['content'] if isinstance(m[-1]['content'], str) else ''
    yield '[happy] Ага.'
app.generate_stream = fake_tr
def chat_msg(msg, **kw):
    r = urllib.request.Request('http://127.0.0.1:8915/chat', json.dumps(dict({'message': msg}, **kw)).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    with urllib.request.urlopen(r) as x: x.read()
chat_msg('Падает вот так:\n' + TRACE, agent=True, work=True)
ok('trace on: the program analysis rides next to the message', 'Разбор программы' in seen['last'] and 'pricing.py:7' in seen['last'])
chat_msg('Падает вот так:\n' + TRACE, agent=True)
ok('trace off: no analysis in everyday talk', 'Разбор программы' not in seen['last'])

# ---- computer diagnostics through the chat ----
def fake_env(m, model=None, vision=False, max_tokens=800, **kw):
    seen['prompt'] = m[0]['content']
    yield '[happy] Гляну. [env:port:3000]'
app.generate_stream = fake_env
ev = chat(agent=True, work=True)
ep = [e['env'] for e in ev if 'env' in e]
ok('env on: a request becomes a plate', len(ep) == 1 and ep[0]['scope'] == 'кто занимает порт 3000' and '[env:что]' in seen['prompt'])
c, b = post('/env/run', {'token': ep[0]['token']})
ok('env: the press returns the program report', c == 200 and 'ДИАГНОСТИКА КОМПЬЮТЕРА' in b['text'])
c, b = post('/env/run', {'token': ep[0]['token']})
ok('env: the press works once', c == 403)
ev = chat(agent=True)
ok('env off: nothing happens', not any('env' in e for e in ev) and '[env:что]' not in seen['prompt'])
