"""The special faces of her model ([fx:tears], [disgusted], [scared]...): the vocabulary, what she is told, how rarely they are shown, and the page that plays them."""
import os
import sys, re, json, tempfile, pathlib, threading, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import faces, app, character, voice, audit
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
character.MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'; app.load_memory()   # never her real memory
audit.FILE = pathlib.Path(tempfile.mkdtemp()) / 'journal.jsonl'

# the vocabulary
ok('disgust and fear are moods now', {'disgusted', 'scared'} <= set(app.EMOTIONS))
ok('they have a voice and a mood effect', {'disgusted', 'scared'} <= set(voice.PROSODY) and {'disgusted', 'scared'} <= set(character.MOOD_DELTA))
ok('the protocol tells her about them', '[disgusted]' in app.PROTOCOL and '[scared]' in app.PROTOCOL)
ok('every special face is a valid tag', all('fx:' + n in app.VALID_TAGS for n in faces.FX))
script, spoken = app.clean_script('[disgusted] Фу. [fx:eyeroll] Ну-ну. [fx:bogus] Да. [shake]')
ok('known tags stay, unknown ones are dropped', '[disgusted]' in script and '[fx:eyeroll]' in script and 'bogus' not in script and spoken == 'Фу. Ну-ну. Да.')

# what the page may name, and what she is told
ok('only known names, once, in a stable order', faces.known(['panic', 'tears', 'tears', 'nope', 5, None]) == ['tears', 'panic'])
ok('garbage is no list', faces.known('tears') == [] and faces.known(None) == [] and faces.known({'a': 1}) == [])
ok('no special faces: no note', faces.hint([]) == '' and faces.hint(None) == '')
h = faces.hint(['tears', 'eyeroll'])
ok('she is told only about the faces her model has', '[fx:tears]' in h and '[fx:eyeroll]' in h and '[fx:hearts]' not in h)
ok('and that they are hers', 'свободно' in h)

# no rate limit: she may use them as she likes
ok('there is no limiter any more', not hasattr(faces, 'Limiter'))
h2 = faces.hint(['tears'], ['wave'])
ok('she is told they are hers to use freely', 'свободно' in h2 and 'не чаще' not in h2)

# the page: the same names, the mood faces, and it tells the server what the model has
js = open(os.path.join(ROOT, 'web', 'avatar.js'), encoding='utf-8').read()
body = re.search(r'const FX_KEYWORDS = \{(.*?)\n\};', js, re.S).group(1)
ok('the page knows exactly the names the server knows', set(re.findall(r'(\w+): /', body)) == set(faces.FX))
ok('the page has the new moods', re.search(r'disgusted:\s*\{', js) and re.search(r'scared:\s*\{', js))
appjs = open(os.path.join(ROOT, 'web', 'app.js'), encoding='utf-8').read()
ok('the page names its special faces in every request', 'fx: avatar.availableFx()' in appjs and 'availableFx()' in js)

# in the conversation
seen = {}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    seen['last'] = m[-1]['content'] if isinstance(m[-1]['content'], str) else ''
    yield from seen['reply']
app.generate_stream = fake
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8806), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def chat(text, **kw):
    r = urllib.request.Request('http://127.0.0.1:8806/chat', json.dumps(dict({'message': text}, **kw)).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    with urllib.request.urlopen(r) as x: return [json.loads(l) for l in x.read().decode().splitlines() if l]
def scripts(ev):
    return ' '.join(e.get('script', '') for e in ev)

seen['reply'] = ['[disgusted] Фу, какая гадость. [fx:eyeroll] Серьёзно?']
ev = chat('я съел сырой лук с шоколадом', fx=['eyeroll', 'tears', 'nope'])
ok('she is told what her model has', '[fx:eyeroll]' in seen['last'] and '[fx:tears]' in seen['last'] and 'nope' not in seen['last'])
ok('the faces reach the page', '[disgusted]' in scripts(ev) and '[fx:eyeroll]' in scripts(ev))
seen['reply'] = ['[sad] Ох. [fx:tears] Мне жаль.']
ev = chat('у меня плохие новости', fx=['eyeroll', 'tears'])
ok('right after one, the next may have one too: no limit', '[sad]' in scripts(ev) and '[fx:tears]' in scripts(ev))
seen['reply'] = ['[happy] Хорошо.']
chat('как дела?', fx=['tears']); chat('как погода?', fx=['tears'])
seen['reply'] = ['[shy] Ой. [fx:blush] Спасибо. [fx:tears] Правда.']
ev = chat('ты милая', fx=['blush', 'tears'])
ok('two in one reply are allowed', scripts(ev).count('[fx:') == 2)
ev = chat('привет', fx=[])
ok('a model without special faces: no note', 'особые выражения лица' not in seen['last'])
ev = chat('привет', fx='junk')
ok('junk from the page is ignored', 'особые выражения лица' not in seen['last'])

# models whose expression files say nothing (1.exp3.json, Button7): the display name of their parameter does
d = pathlib.Path(tempfile.mkdtemp())
(d / 'm.cdi3.json').write_text(json.dumps({'Parameters': [{'Id': 'Param30', 'Name': '脸红'}, {'Id': 'Param31', 'Name': '哭'}, {'Id': 5, 'Name': 'x'}, 'junk']}), encoding='utf-8')
ok('parameter display names are read', app.parameter_labels(d) == {'Param30': '脸红', 'Param31': '哭'})
(d / 'm.cdi3.json').write_text('not json', encoding='utf-8')
ok('a broken file gives nothing, not a crash', app.parameter_labels(d) == {})
ok('no cdi file: nothing', app.parameter_labels(pathlib.Path(tempfile.mkdtemp())) == {})
listed = app.list_models() if hasattr(app, 'list_models') else []
ok('every listed model carries its labels', all(isinstance(m.get('labels'), dict) for m in listed))
ok('the page reads the label of the first parameter', "info.labels" in js and 'exText' in js)

# the model's own movements: [mo:name]
ok('motions are valid tags', all('mo:' + n in app.VALID_TAGS for n in faces.MOTIONS))
script, spoken = app.clean_script('[happy] Привет! [mo:wave] Рада тебя видеть. [mo:bogus] Да.')
ok('known movement stays, unknown is dropped', '[mo:wave]' in script and 'bogus' not in script and spoken == 'Привет! Рада тебя видеть. Да.')
mb = re.search('const MOTION_KEYWORDS = [{](.*?)[}];', js, re.S).group(1)
ok('the page knows exactly the movements the server knows', set(re.findall(r'(\w+): /', mb)) == set(faces.MOTIONS))
h = faces.hint([], ['wave', 'nope'])
ok('movements alone are told', '[mo:wave]' in h and 'nope' not in h and 'свободно' in h)
ok('faces and movements together', '[fx:tears]' in faces.hint(['tears'], ['wave']) and '[mo:wave]' in faces.hint(['tears'], ['wave']))
ok('junk motions: no note', faces.hint([], 'wave') == '' and faces.known_motions(None) == [])
ok('the page names its movements in every request', 'mo: avatar.availableMotions()' in appjs and 'availableMotions()' in js and 'playMotion' in js)
ok('listed models carry their movement files', all(isinstance(m.get('motions'), list) for m in listed))
seen['reply'] = ['[happy] Привет! [mo:wave] Рада тебя видеть.']
ev = chat('привет, я вернулся', mo=['wave', 'bogus'], fx=[])
ok('she is told her movements and may use one', '[mo:wave]' in seen['last'] and 'bogus' not in seen['last'] and '[mo:wave]' in scripts(ev))

# the curve player against known values (node, when installed)
import subprocess, shutil
if shutil.which('node'):
    NL = chr(10)
    code = ("const fs=require('fs');const js=fs.readFileSync(process.argv[1],'utf8').split(String.fromCharCode(13)).join('');"
            "const i=js.indexOf('function curveValue');const cv=new Function(js.slice(i,js.indexOf(String.fromCharCode(10)+'}',i)+2)+';return curveValue;')();"
            "console.log(JSON.stringify([cv([0,0,0,2,1],1),cv([0,0,1,0.5,0,1.5,1,2,1],2),cv([0,0,2,1,1],0.5),cv([1,5,0,2,6],0.2),cv([0,0,3,1,1],0.5),cv([0,0,0,1,1],9)]));")
    r = subprocess.run(['node', '-e', code, os.path.join(ROOT, 'web', 'avatar.js')], capture_output=True, text=True, timeout=30)
    vals = json.loads(r.stdout) if r.returncode == 0 else []
    ok('curve player: linear, bezier end, stepped, before start, inverse stepped, after end',
       len(vals) == 6 and abs(vals[0] - 0.5) < 1e-6 and abs(vals[1] - 1) < 1e-3 and vals[2] == 0 and vals[3] == 5 and vals[4] == 1 and vals[5] == 1)
