import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
from luna.dev import devtools, unreal_bridge as ub
from http.server import ThreadingHTTPServer

# pull_code: streaming in odd chunks gives the same blocks as one piece
raw = 'Вот. [happy] Смотри, как это делается.\n```python\nprint("hi [nod]")\nx = [1, 2]\n```\nГотово, проверь. Ещё ```guide\n1. Шаг\n2. Шаг\n``` конец.'
def run_stream(chunks):
    buf, out = '', []
    for c in chunks:
        buf += c
        segs, held = app.pull_code(buf)
        out += [s for s in segs if s[0] == 'code']
        buf = ''.join(v for k, v in segs if k == 'text') if False else held
        # emulate chat_turn: only the unfinished fence is held, text is consumed
    return out
whole = [s for s in app.pull_code(raw, True)[0] if s[0] == 'code']
print('blocks whole:', [(b[1]['lang'], b[1]['text'][:12]) for b in whole])
buf, got = '', []
for i in range(0, len(raw), 7):
    buf += raw[i:i + 7]
    segs, held = app.pull_code(buf)
    got += [s[1] for s in segs if s[0] == 'code']
    buf = held
segs, held = app.pull_code(buf, True)
got += [s[1] for s in segs if s[0] == 'code']
print('blocks streamed 7 chars at a time:', len(got), [g['lang'] for g in got])
print('unclosed fence at end (final):', app.pull_code('Вот код ```js\nlet a = 1', True)[0])

# topics and the prompt block
for t in ['как подключить Unreal?', 'как включить анрил', 'ренпай label', 'help with my Godot project', 'bug in my function', '언리얼 연결', 'ユニティ', 'привет как дела']:
    print(repr(t), '->', devtools.topics(t))
app.AGENT = True
p = app.system_prompt('как мне подключить Unreal Engine к тебе?')
print('prompt has unreal guide:', 'Python Editor Script Plugin' in p, '| facts:', 'AsianLegends' in p, '| probe line:', 'Проверка прямо сейчас' in p)
print('no topic -> no dev block:', 'разработчица' not in app.system_prompt('привет'))
print('paths never in prompt:', 'D:\\' not in p)

# a code file: found by name, shown only with a token, secrets refused
tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / 'Player.cs').write_text('class Player { }', encoding='utf-8')
(tmp / '.env').write_text('KEY=1', encoding='utf-8')
(tmp / 'my_secret.py').write_text('x=1', encoding='utf-8')
devtools._code['items'] = [{'label': n, 'path': str(tmp / n)} for n in ('Player.cs', '.env', 'my_secret.py')]
devtools._code['t'] = 9e18
print('find Player:', [x['label'] for x in devtools.find_code('player')], '| find env:', devtools.find_code('.env'), '| secret:', devtools.find_code('secret'))
tok = devtools.find_code('player.cs')[0]['token']
print('read:', devtools.read_code(tok))
try: devtools.read_code(tok)
except PermissionError: print('replay refused')
devtools.FOUND['t2'] = {'path': str(tmp / '.env'), 'label': '.env', 't': 9e18}
try: devtools.read_code('t2')
except OSError: print('direct secret refused')

# server: a reply with code + read tag
__import__('luna.core.character', fromlist=['_']).MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'
app.KEY = 'dummy'; app.load_memory()
def fake(m, model=None, **kw):
    yield '[happy] Держи, вот пример. [read:Player.cs]\n```csharp\nvoid Update() { }\n```\n'
    yield 'Вставь это в скрипт.'
app.generate_stream = fake
srv = ThreadingHTTPServer(('127.0.0.1', 8785), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d):
    r = urllib.request.Request('http://127.0.0.1:8785' + path, json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
big = 'вот код:\n' + 'x = 1\n' * 1500
st, body = post('/chat', {'message': big, 'agent': True, 'work': True})
ev = [json.loads(l) for l in body.splitlines() if l]
print('long message accepted:', st, '| order:', [list(e)[0] for e in ev])
print('spoken has no code:', [e['answer'] for e in ev if 'answer' in e])
print('history keeps code, truncated user:', any('```csharp' in h['content'] for h in app.HISTORY), max(len(h['content']) for h in app.HISTORY if h['role'] == 'user') <= app.MAX_STORED)
rf = [e['readfile'] for e in ev if 'readfile' in e]
print('readfile plate:', [(i['label']) for r in rf for i in r['items']])
print('/code/read bad token:', post('/code/read', {'token': 'zz'})[0])
if rf:
    print('/code/read ok:', post('/code/read', {'token': rf[0]['items'][0]['token']}))
