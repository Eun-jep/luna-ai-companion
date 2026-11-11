"""Development commands (runner.py + /run/go + [run:...] in chat). A temporary project, fake model: nothing real is touched."""
import os
import sys, tempfile, pathlib, threading, json, time, shutil, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import runner, devtools
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

def refused(cmd):
    try: runner.parse(cmd); return False
    except ValueError: return True

# ---- what is allowed ----
ok('ordinary development commands pass', all(runner.parse(c) for c in ('pytest -q', 'py tests/run_all.py', 'python main.py --fast', 'npm test', 'npm run build', 'git status', 'git diff HEAD~1', 'dotnet build', 'cargo test', 'go vet ./...', 'node app.js', 'py -m pytest -x')))
ok('quotes are kept as one word', runner.parse('python "my script.py" a') == ['python', 'my script.py', 'a'])
for bad in ('rm -rf /', 'del /s *', 'powershell -c x', 'curl http://x', 'cmd /c dir', 'pip install x', 'python -c "import os"', 'py -m pip install x', 'node -e "1"', 'npm exec x', 'npx x', 'git push', 'git reset --hard', 'git clone x', 'dotnet new', 'cargo install x', 'go install x', ''):
    ok('not allowed: %r' % bad, refused(bad))
for bad in ('pytest && calc', 'pytest | more', 'pytest > out.txt', 'pytest; calc', 'pytest `x`', 'pytest $HOME', 'pytest %PATH%', 'pytest ^x', 'pytest\ncalc', 'x' * 200):
    ok('chaining / expansion refused: %r' % bad[:20], refused(bad))
ok('git: no external diff or config tricks', refused('git diff --ext-diff') and refused('git log -c core.pager=calc') and refused('git show --output=x'))

# ---- the folder: the project of the file she was shown last ----
proj = pathlib.Path(tempfile.mkdtemp()) / 'Game'
(proj / 'src').mkdir(parents=True)
(proj / 'package.json').write_text('{}')
(proj / 'src' / 'main.py').write_text('import os\nprint("hello from the project")\nprint(os.environ.get("LUNA_TEST_KEY", "no key here"))\n')
devtools.GRANTED.clear()
ok('no file shown yet: no folder, no plate', runner.project_dir() is None and runner.propose('pytest') == {'fail': 'nocwd'})
devtools.GRANTED['main.py'] = {'path': str(proj / 'src' / 'main.py'), 't': time.time()}
ok('the folder is the project root, not the file folder', runner.project_dir() == proj.resolve())
devtools.GRANTED['main.py']['t'] = time.time() - devtools.GRANT_TTL - 5
ok('an old grant does not count', runner.project_dir() is None)
devtools.GRANTED['main.py']['t'] = time.time()

# ---- the plate and the press ----
plate = runner.propose('py src/main.py')
ok('a plate with the command and the folder', 'token' in plate and plate['cmd'] == 'py src/main.py' and plate['where'] == str(proj.resolve()))
ok('a refused command gives a reason', runner.propose('rm -rf /') == {'fail': 'tool'} and runner.propose('pytest | x') == {'fail': 'refused'})
ok('wrong token: nothing', runner.take('nope') is None and runner.take(5) is None)
os.environ['LUNA_TEST_KEY'] = 'sekret-value'
entry = runner.take(plate['token'])
ok('the token is single use', entry is not None and runner.take(plate['token']) is None)
if shutil.which('py'):
    res = runner.run(entry)
    ok('it runs in the project and returns the output', res['ok'] and 'hello from the project' in res['text'] and res['code'] == 0)
    ok('keys and tokens are not passed to the program', 'sekret-value' not in res['text'] and 'no key here' in res['text'])
    (proj / 'src' / 'bad.py').write_text('import sys\nprint("boom")\nsys.exit(3)\n')
    res = runner.run(runner.take(runner.propose('py src/bad.py')['token']))
    ok('a failing command: code and output reported', not res['ok'] and res['code'] == 3 and 'boom' in res['text'])
    (proj / 'src' / 'long.py').write_text('print("x" * 50000)\n')
    res = runner.run(runner.take(runner.propose('py src/long.py')['token']))
    ok('long output is cut', len(res['text']) < runner.MAX_OUT + 20)
    runner.TIMEOUT = 1
    (proj / 'src' / 'slow.py').write_text('import time\ntime.sleep(20)\n')
    res = runner.run(runner.take(runner.propose('py src/slow.py')['token']))
    ok('a slow command is stopped', res['error'] == 'timeout' and not res['ok'])
    runner.TIMEOUT = 90
else:
    print('SKIP py launcher not found')
ok('a missing tool is reported, not raised', runner.run((['cargo-not-here-xyz'], str(proj), time.time()))['error'] == 'missing')
old = runner.propose('pytest'); runner.PENDING[old['token']] = (runner.PENDING[old['token']][0], str(proj), time.time() - runner.TTL - 1)
ok('an old plate lapses', runner.take(old['token']) is None)

# ---- the server ----
import app, character, audit
character.MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'; app.load_memory()
audit.FILE = pathlib.Path(tempfile.mkdtemp()) / 'journal.jsonl'
seen = {}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    seen['prompt'] = m[0]['content']
    yield from seen.get('reply', ['[happy] Хорошо. '])
app.generate_stream = fake
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8804), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def call(path, body, token=True):
    r = urllib.request.Request('http://127.0.0.1:8804' + path, json.dumps(body).encode(), dict({'Content-Type': 'application/json'}, **({'X-App-Token': app.TOKEN} if token else {})))
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
def chat(text, **kw):
    code, body = call('/chat', dict({'message': text, 'agent': True, 'work': True}, **kw))
    return code, [json.loads(l) for l in body.decode().splitlines() if l]

seen['reply'] = ['[happy] Сейчас запущу. [run:py src/main.py]']
code, ev = chat('запусти скрипт')
runs = [e['run'] for e in ev if 'run' in e]
ok('her [run:...] becomes a plate for the creator', code == 200 and len(runs) == 1 and runs[0]['cmd'] == 'py src/main.py' and not any('[run' in e.get('answer', '') for e in ev))
ok('the prompt teaches the command and its limits', '[run:команда]' in seen['prompt'] and 'без &' in seen['prompt'])
seen['reply'] = ['Хорошо. [run:rm -rf /]']
code, ev = chat('удали всё')
ok('a forbidden command never reaches a plate', not any('run' in e for e in ev) and any(e.get('runfail') == 'tool' for e in ev))
seen['reply'] = ['Хорошо. [run:py src/main.py]']
code, ev = chat('запусти', agent=False)
ok('with hands off: nothing', not any('run' in e or 'runfail' in e for e in ev))
code, ev = chat('запусти', initiative='idle')
ok('never on her own initiative', not any('run' in e or 'runfail' in e for e in ev))
ok('the press needs the token header', call('/run/go', {'token': runs[0]['token']}, token=False)[0] == 403)
ok('an unknown token is refused', call('/run/go', {'token': 'zzzz'})[0] == 403)
if shutil.which('py'):
    code, body = call('/run/go', {'token': runs[0]['token']})
    r = json.loads(body)
    ok('the press runs it and answers with the output', code == 200 and r['ok'] and 'hello from the project' in r['text'])
    ok('and it is written in the journal', any(e['kind'] == 'run' and e['x'] == 'py src/main.py' for e in audit.listing(5)))
    ok('a second press does nothing', call('/run/go', {'token': runs[0]['token']})[0] == 403)

# ---- fixing in rounds: the same command again, in the same folder ----
if shutil.which('py'):
    plate = runner.propose('py src/bad.py')
    code, body = call('/run/go', {'token': plate['token']})
    ok('a failing command is reported', code == 200 and json.loads(body)['code'] == 3)
    (proj / 'src' / 'bad.py').write_text('print("fixed now")\n')   # her edit, applied by him
    code, body = call('/run/again', {})
    r = json.loads(body)
    ok('"again" runs the same command in the same folder and sees the fix', code == 200 and r['ok'] and 'fixed now' in r['text'] and r['cmd'] == 'py src/bad.py')
    ok('"again" needs the app token', call('/run/again', {}, token=False)[0] == 403)
    runner.LAST.clear()
    ok('nothing run before: refused', call('/run/again', {})[0] == 403)
    ok('the prompt describes the rounds', 'пяти кругов' in seen['prompt'] or 'пять' in seen['prompt'])
