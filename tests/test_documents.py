import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
from luna.hands import office
from http.server import ThreadingHTTPServer
tmp = pathlib.Path(tempfile.mkdtemp())
office.FOLDER = tmp / 'Luna'
__import__('luna.core.character', fromlist=['_']).MEMORY_FILE = tmp / 'memory.json'; app.load_memory()
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

SPEC = {'type': 'pptx', 'title': 'Отчёт', 'slides': [{'layout': 'title', 'title': 'Отчёт', 'subtitle': 'Q3'}, {'title': 'Итоги', 'bullets': ['Рост', 'Клиенты']}]}
mode = {'reply': None}
def fake(m, model=None, vision=False, max_tokens=800):
    mode['max_tokens'] = max_tokens; mode['prompt'] = m[0]['content']
    for piece in mode['reply']:
        yield piece
app.generate_stream = fake
srv = ThreadingHTTPServer(('127.0.0.1', 8793), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d):
    r = urllib.request.Request('http://127.0.0.1:8793' + path, json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
def chat(**kw):
    c, b = post('/chat', dict({'message': 'сделай презентацию', 'agent': True, 'work': True}, **kw))
    return c, [json.loads(l) for l in b.splitlines() if l]

mode['reply'] = ['[happy] Конечно, милый, я подготовила. ', '```lunadoc\n' + json.dumps(SPEC, ensure_ascii=False)[:40], json.dumps(SPEC, ensure_ascii=False)[40:] + '\n```\n', 'Нажми «Создать», хорошо?']
c, ev = chat()
docs = [e['document'] for e in ev if 'document' in e]
ok('document plate sent', c == 200 and len(docs) == 1 and docs[0]['app'] == 'PowerPoint' and docs[0]['size'] == 2)
ok('no code event, JSON not spoken', not any('code' in e for e in ev) and not any('{' in e.get('answer', '') for e in ev))
ok('she spoke warm words around it', len([e for e in ev if 'answer' in e]) >= 2)
ok('long reply allowed (max_tokens 6000)', mode['max_tokens'] == 6000)
ok('prompt explains lunadoc and keeps the warm part', 'lunadoc' in mode['prompt'] and 'заботливая дочь' in mode['prompt'])
ok('history keeps the whole spec for revisions', any('"slides"' in h['content'] for h in app.HISTORY))
ok('no file before the press', not office.FOLDER.exists() or not list(office.FOLDER.iterdir()))
c, b = post('/doc/make', {'token': docs[0]['token'], 'open': False}); r = json.loads(b)
ok('press -> file created', c == 200 and r['ok'] and (office.FOLDER / r['name']).is_file())
ok('replay -> 403 doc:token', post('/doc/make', {'token': docs[0]['token']}) == (403, '{"error": "doc:token"}'))
ok('bad token -> 403', post('/doc/make', {'token': 'zz'})[0] == 403)

c, ev = chat(initiative='idle', message='')
mode['reply'] = ['[happy] Сама сделала. ```lunadoc\n' + json.dumps(SPEC) + '\n``` Вот.']
c, ev = chat(initiative='idle')
ok('her own initiative gets no plate', not any('document' in e for e in ev))
mode['reply'] = ['Хорошо. ```lunadoc\n' + json.dumps(SPEC) + '\n``` Готово.']
c, ev = chat(agent=False)
ok('agent switch off -> no plate', not any('document' in e for e in ev))
mode['reply'] = ['Хорошо. ```lunadoc\n{not json}\n``` Готово.']
c, ev = chat()
ok('broken JSON -> docfail, no crash', c == 200 and any('docfail' in e for e in ev))
mode['reply'] = ['Хорошо. ```lunadoc\n' + json.dumps({'type': 'xlsx', 'title': 'Бюджет', 'sheets': [{'name': 'A', 'header': ['x', 'y'], 'rows': [['a', 1], ['=SUM', '=SUM(B2:B2)']]}]}) + '\n``` Держи.']
c, ev = chat()
d = [e['document'] for e in ev if 'document' in e][0]
c, b = post('/doc/make', {'token': d['token'], 'open': False})
ok('xlsx via server', c == 200 and json.loads(b)['name'].endswith('.xlsx'))
print(sorted(p.name for p in office.FOLDER.iterdir()))
