"""The daily stand-up in work mode (standup.py + the lunastandup block in app.py). Fake model, temporary file."""
import os
import sys, tempfile, pathlib, json, threading, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.skills import standup
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
tmp = pathlib.Path(tempfile.mkdtemp())
standup.FILE = str(tmp / 'standup.json')

ok('nothing yet', standup.load() == [])
e = standup.save(json.dumps({'yesterday': ['починил логин'], 'today': ['тесты на платежи', ' '], 'blockers': 'жду доступ к стенду'}), today='2026-11-02')
ok('a note is kept, blanks dropped, a string becomes a list', e['today'] == ['тесты на платежи'] and e['blockers'] == ['жду доступ к стенду'])
ok('it survives a reload', standup.load()[0]['date'] == '2026-11-02')
standup.save(json.dumps({'today': ['ревью']}), today='2026-11-02')
ok('one note per day: the second replaces the first', len(standup.load()) == 1 and standup.load()[0]['today'] == ['ревью'])
ok('junk is refused', standup.save('не json') is None and standup.save('[1]') is None and standup.save('{"today": []}') is None and len(standup.load()) == 1)
for i in range(70):
    standup.save(json.dumps({'today': ['x%d' % i]}), today='2027-01-%02d' % (i % 28 + 1) if i < 28 else '2027-02-%02d' % (i % 28 + 1))
ok('only the latest are kept', len(standup.load()) <= standup.KEEP)

standup.clear()
standup.save(json.dumps({'yesterday': ['а'], 'today': ['доделать отчёт'], 'blockers': ['нет доступа']}), today='2026-11-02')
b = standup.block(today='2026-11-03')
ok('the block explains the stand-up and the format', 'lunastandup' in b and 'по одному вопросу' in b)
ok('she asks how yesterday’s plan went', 'доделать отчёт' in b and 'нет доступа' in b and 'как вышло' in b)
ok('no entry for today yet: one passing offer', 'ещё нет' in b)
ok('an entry for today: no new offer', 'уже записан' in standup.block(today='2026-11-02'))
ok('the block is not endless', len(b) <= 3000)

# through the chat
import app
from luna.core import character
character.MEMORY_FILE = tmp / 'memory.json'; app.load_memory()
reply = {'text': ''}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    reply['prompt'] = m[0]['content']
    yield reply['text']
app.generate_stream = fake
app.generate = lambda m: 'нет'
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8916), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def chat(**kw):
    r = urllib.request.Request('http://127.0.0.1:8916/chat', json.dumps(dict({'message': 'ну вот такой стендап'}, **kw)).encode(),
                               {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    with urllib.request.urlopen(r) as x:
        return [json.loads(l) for l in x.read().decode().splitlines() if l.strip()]

standup.clear()
reply['text'] = '[happy] Записываю.\n```lunastandup\n{"yesterday":["ревью"],"today":["релиз"],"blockers":[]}\n```\n'
ev = chat(agent=True, work=True)
ok('work mode: the block is saved and the page is told', any(e.get('standup') for e in ev) and standup.load()[-1]['today'] == ['релиз'])
ok('the block is not shown as code', not any('code' in e for e in ev))
ok('the work prompt has the stand-up section', 'lunastandup' in reply['prompt'])
standup.clear()
ev = chat(agent=True)
ok('work mode off: nothing is written, the block is not in the prompt', standup.load() == [] and 'lunastandup' not in reply['prompt'])
standup.save(json.dumps({'today': ['a']}))
req = urllib.request.Request('http://127.0.0.1:8916/forget', b'{}', {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
urllib.request.urlopen(req).read()
ok('forgetting also clears the notes', standup.load() == [])
