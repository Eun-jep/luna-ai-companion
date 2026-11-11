"""The song library (studio.py + /studio/* + the perform event in chat). Temporary folder, fake model: nothing real is touched."""
import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.hands import studio
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

tmp = pathlib.Path(tempfile.mkdtemp())
studio.DIR, studio.INDEX = tmp / 'songs', tmp / 'songs' / 'library.json'
MP3 = b'ID3\x04\x00' + b'\x00' * 3000
WAV = b'RIFF\x24\x00\x00\x00WAVEfmt ' + b'\x00' * 3000

# ---- formats are told by the first bytes, not by the name ----
ok('mp3 / wav / ogg / flac / m4a recognised', [studio.kind(h) for h in (b'ID3\x03', b'\xff\xfb\x90\x00', WAV[:16], b'OggS\x00\x02', b'fLaC\x00', b'\x00\x00\x00\x20ftypM4A ')] == ['mp3', 'mp3', 'wav', 'ogg', 'flac', 'm4a'])
for bad in (b'MZ\x90\x00' + b'\x00' * 20, b'#!/bin/sh\n', b'<html>', b'PK\x03\x04', b''):
    ok('not audio refused: %r' % bad[:6], studio.kind(bad) == '')
for bad, why in ((MP3[:100], 'size'), (b'MZ' + b'\x00' * 3000, 'format'), ('text', 'size')):
    try: studio.add('x.mp3', bad); r = ''
    except ValueError as e: r = str(e)
    ok('add refused (%s)' % why, r == why)
ok('nothing was stored by refused adds', studio.load() == [])

# ---- names ----
ok('title from a file name', studio.clean_title('C:\\Music\\Nier_Automata - Weight of the World.mp3') == 'Nier Automata - Weight of the World')
ok('title: no folders, no odd characters, limited', studio.clean_title('../../etc/<a>|b?.mp3') == 'a b' and len(studio.clean_title('x' * 500)) == 80)
ok('empty name gets a default', studio.clean_title('') == 'Песня' and studio.clean_title('.mp3') != '')

# ---- the library ----
a = studio.add('Дождь.mp3', MP3)
b = studio.add('Weight of the World.wav', WAV)
c = studio.add('Колыбельная для кота.mp3', MP3)
ok('files are named by the program, not by the creator', (studio.DIR / (a['id'] + '.mp3')).is_file() and sorted(p.name for p in studio.DIR.iterdir() if p.suffix != '.json') == sorted([a['id'] + '.mp3', b['id'] + '.wav', c['id'] + '.mp3']))
ok('the list survives a reload', [s['title'] for s in studio.load()] == ['Дождь', 'Weight of the World', 'Колыбельная для кота'])
ok('path only for real ids', studio.path(a['id']).is_file() and studio.path('../../app') is None and studio.path('0' * 12) is None and studio.path(5) is None)
ok('info: tempo and length are validated', studio.set_info(a['id'], 120.4, 200)['bpm'] == 120 and studio.set_info(a['id'], 5, True)['bpm'] == 120 and studio.get(a['id'])['secs'] == 200)
ok('rename', studio.rename(a['id'], 'Дождь в мае')['title'] == 'Дождь в мае')
studio.rename(a['id'], 'Дождь')

# ---- finding the song she was asked for ----
ok('by title', studio.find('спой Дождь')['id'] == a['id'] and studio.find('Спой, пожалуйста, песню «Колыбельная для кота»')['id'] == c['id'])
ok('by a part of the title', studio.find('спой колыбельную')['id'] == c['id'] and studio.find('спой weight of the world')['id'] == b['id'])
ok('a request for a theme names no song', studio.find('спой про дождь и осень') is None and studio.find('спой мне') is None and studio.find('спой что-нибудь весёлое') is None)
ok('empty library finds nothing', studio.find('') is None)

# ---- the server ----
import app
from luna.core import character
character.MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'; app.load_memory()
seen = {}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    seen['prompt'] = m[0]['content']
    yield '[happy] Хорошо. '
app.generate_stream = fake
app.generate = lambda m: 'не умею'
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8911), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def call(path, body=None, raw=None, token=True, headers=None):
    data = raw if raw is not None else json.dumps(body or {}).encode()
    h = {'Content-Type': 'application/json'}
    if token: h['X-App-Token'] = app.TOKEN
    h.update(headers or {})
    r = urllib.request.Request('http://127.0.0.1:8911' + path, data, h)
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read(), x.headers
    except urllib.error.HTTPError as e: return e.code, e.read(), e.headers

ok('no token: refused', call('/studio/list', token=False)[0] == 403 and call('/studio/add', raw=MP3, token=False)[0] == 403)
code, body, _ = call('/studio/list')
ok('list', code == 200 and len(json.loads(body)['songs']) == 3)
code, body, hd = call('/studio/file', {'id': a['id']})
ok('file comes back as audio', code == 200 and body == MP3 and hd['Content-Type'] == 'audio/mpeg' and call('/studio/file', {'id': '../../app'})[0] == 404 and call('/studio/file', {})[0] == 404)
code, body, _ = call('/studio/add', raw=MP3, headers={'X-Name': '%D0%9D%D0%BE%D0%B2%D0%B0%D1%8F%20%D0%BF%D0%B5%D1%81%D0%BD%D1%8F.mp3', 'Content-Type': 'application/octet-stream'})
new = json.loads(body)
ok('add by upload', code == 200 and new['song']['title'] == 'Новая песня' and len(new['songs']) == 4)
ok('a program is not accepted as a song', call('/studio/add', raw=b'MZ' + b'\x00' * 3000, headers={'X-Name': 'x.mp3'})[0] == 415)
ok('a tiny file is refused', call('/studio/add', raw=b'ID3', headers={'X-Name': 'x.mp3'})[0] == 413)
code, body, _ = call('/studio/info', {'id': new['song']['id'], 'bpm': 98, 'secs': 61})
ok('info over the wire', code == 200 and json.loads(body)['song']['bpm'] == 98 and call('/studio/info', {'id': 'zzzzzzzzzzzz'})[0] == 404)
code, body, _ = call('/studio/remove', {'id': new['song']['id']})
ok('remove deletes the file too', code == 200 and len(json.loads(body)['songs']) == 3 and not (studio.DIR / (new['song']['id'] + '.mp3')).exists() and call('/studio/remove', {'id': new['song']['id']})[0] == 404)
ok('unknown studio path', call('/studio/evil')[0] == 404)

# ---- chat: asked for a song of the library -> the recording is performed, nothing is made up ----
def chat(text, **kw):
    code, body, _ = call('/chat', dict({'message': text}, **kw))
    return code, [json.loads(l) for l in body.decode().splitlines() if l]
code, ev = chat('спой Дождь')
perf = [e['perform'] for e in ev if 'perform' in e]
ok('asked for a known song: perform', code == 200 and len(perf) == 1 and perf[0]['id'] == a['id'] and perf[0]['bpm'] == 120 and not any('song' in e for e in ev))
code, ev = chat('спой про осень')
ok('a theme, not a title: nothing is performed and nothing is made up', not any('perform' in e or 'song' in e for e in ev))
ok('she knows she only performs recordings, and what is in the library', 'сама ты песни не сочиняешь' in seen['prompt'] and '«Дождь»' in seen['prompt'] and 'lunasong' not in seen['prompt'])
code, ev = chat('расскажи про Дождь')
ok('only a request to sing performs', not any('perform' in e for e in ev))
code, ev = chat('спой Дождь', initiative=True)
ok('never on her own initiative', not any('perform' in e for e in ev))

# ---- a cover in her own voice ----
code, body, _ = call('/studio/add', raw=MP3, headers={'X-Name': 'My%20Cover.mp3', 'X-Her': '1', 'Content-Type': 'application/octet-stream'})
her = json.loads(body)['song']
ok('a cover is stored with her mark, a plain song is not marked', code == 200 and her.get('her') is True and 'her' not in a)
code, ev = chat('спой My Cover')
perf = [e['perform'] for e in ev if 'perform' in e]
ok('the perform event says it is her voice', len(perf) == 1 and perf[0]['her'] is True)
ok('she is told which recordings are her own voice, and not to invent how', '«My Cover» (кавер твоим голосом)' in seen['prompt'] and 'не придумывай подробностей' in seen['prompt'])
code, ev = chat('спой Дождь')
ok('a plain recording is still not hers', [e['perform']['her'] for e in ev if 'perform' in e] == [False])
studio.remove(her['id'])
code, ev = chat('спой Дождь')
ok('without any cover the prompt does not mention her voice', 'кавер твоим голосом' not in seen['prompt'])
# the page, the notebook and the strings
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
js = open(os.path.join(ROOT, 'web', 'studio.js'), encoding='utf-8').read()
tr = open(os.path.join(ROOT, 'web', 'i18n.js'), encoding='utf-8').read()
ok('the page has a button for covers in her voice and sends the mark', 'id="songs-add-her"' in html and 'id="songs-file-her"' in html and "'X-Her': '1'" in js and 'song.her' in js)
ok('her-voice strings in all four languages', all(tr.count("'songs.%s':" % k) == 4 for k in ('addher', 'her', 'now.her', 'herhint')))
nb = json.load(open(os.path.join(ROOT, 'studio', 'Luna_cover.ipynb'), encoding='utf-8'))
src = '\n'.join(''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code')
ok('the notebook is valid and has every stage: train, separate, convert, mix', nb['nbformat'] == 4 and all(w in src for w in ('core.py", "train"', 'demucs', 'core.py", "infer"', 'amix')))
ok('the notebook skips empty recordings and never sends anything but the creator\'s own files', 'len(data) > 1024' in src and 'files.upload' in src)
import ast
bad = []
for c in nb['cells']:
    if c['cell_type'] == 'code':
        try: ast.parse('\n'.join('pass' if l.lstrip().startswith(('!', '%')) else l for l in ''.join(c['source']).splitlines()))
        except SyntaxError: bad.append(1)
ok('every notebook cell parses as Python', not bad)
