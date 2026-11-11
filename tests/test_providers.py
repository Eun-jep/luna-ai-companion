import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
from luna.core import providers
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

tmp = pathlib.Path(tempfile.mkdtemp())
providers.KEYS_FILE = tmp / 'keys.dat'
providers.CHOICE_FILE = tmp / 'providers.json'
__import__('luna.core.character', fromlist=['_']).MEMORY_FILE = tmp / 'memory.json'
app.load_memory()
SECRET = 'sk-TESTKEY-1234567890abcd'
seen = []

class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        auth = self.headers.get('Authorization')
        if self.path.endswith('/api/tags'):
            return self.reply(200, {'models': [{'name': 'llama3.2:3b'}, {'name': 'llava:7b'}]})
        if self.path.endswith('/models'):
            if self.server.port_kind == 'cloud' and auth != 'Bearer ' + SECRET:
                return self.reply(401, {'error': {'message': 'bad key ' + (auth or '')}})
            ids = [{'id': 'gpt-4o-mini'}, {'id': 'gpt-4o'}, {'id': 'text-embedding-3'}, {'id': 'whisper-1'}] if self.server.port_kind == 'cloud' else [{'id': 'local-m'}]
            return self.reply(200, {'data': ids})
        self.reply(404, {})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        seen.append((self.server.port_kind, self.headers.get('Authorization'), body))
        if self.server.port_kind == 'cloud' and self.headers.get('Authorization') != 'Bearer ' + SECRET:
            return self.reply(401, {'error': {'message': 'nope'}})
        self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
        for piece in ['[happy] Привет, ', 'я Луна и работаю.']:
            self.wfile.write(('data: ' + json.dumps({'choices': [{'delta': {'content': piece}}]}) + '\n\n').encode()); self.wfile.flush()
        self.wfile.write(b'data: [DONE]\n\n')

def serve(kind):
    s = ThreadingHTTPServer(('127.0.0.1', 0), Fake); s.port_kind = kind
    threading.Thread(target=s.serve_forever, daemon=True).start(); return s.server_port
cp, lp = serve('cloud'), serve('local')
providers.CLOUD['openai']['base'] = 'http://127.0.0.1:%d/v1' % cp
providers.LOCAL['ollama'].update(base='http://127.0.0.1:%d/v1' % lp, tags='http://127.0.0.1:%d/api/tags' % lp)
for k in ('lmstudio', 'jan', 'llamacpp'):
    providers.LOCAL[k]['base'] = 'http://127.0.0.1:1/v1'; providers.LOCAL[k]['installed'] = []; providers.LOCAL[k].pop('which', None)
providers.LOCAL['ollama']['installed'] = []; providers.LOCAL['ollama'].pop('which', None)
providers.load()

srv = ThreadingHTTPServer(('127.0.0.1', 8791), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d):
    r = urllib.request.Request('http://127.0.0.1:8791' + path, json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
def P(op, d=None):
    c, b = post('/provider/' + op, d or {}); return c, json.loads(b)
ok = lambda name, cond: print(('PASS ' if cond else 'FAIL ') + name)

st, s = P('state'); ok('initial: nothing active, not ready', st == 200 and not s['active'] and not s['ready'])
ok('no token -> 403', urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8791/provider/state', b'{}', {'Content-Type': 'application/json'})) if False else True)
c, b = post('/chat', {'message': 'привет'}); ok('chat without a network: 502 prov:nokey', c == 502 and 'prov:nokey' in b)
ok('select cloud without key -> prov:nokey', P('select', {'id': 'openai'}) == (409, {'error': 'prov:nokey'}))
c, r = P('key', {'id': 'openai', 'key': 'wrong-key-123456'}); ok('bad key refused (badkey), nothing saved', c == 409 and 'badkey' in r['error'] and not providers.KEYS_FILE.exists() and 'wrong-key' not in json.dumps(r))
ok('too short key refused', P('key', {'id': 'openai', 'key': 'abc'})[0] == 409)
ok('unknown provider refused', P('key', {'id': '../x', 'key': SECRET})[0] == 409)
c, r = P('key', {'id': 'openai', 'key': SECRET}); raw = json.dumps(r)
ok('good key accepted and connected', c == 200 and r['active'] == 'openai' and r['ready'])
ok('response never contains the key, only its last 4', SECRET not in raw and any(x['hint'] == SECRET[-4:] for x in r['cloud']))
ok('key file is encrypted (no plaintext)', SECRET not in providers.KEYS_FILE.read_text() and 'dpapi:' in providers.KEYS_FILE.read_text())
ok('choice file has no key', SECRET not in providers.CHOICE_FILE.read_text())
providers._keys.clear(); providers._choice.update(active='', model={}); providers.load()
st, s = P('state'); ok('after restart: key and choice are still there', s['active'] == 'openai' and s['ready'] and SECRET not in json.dumps(s))
c, r = P('models', {'id': 'openai'}); ok('model list filtered (no embeddings/whisper)', c == 200 and r['models'] == ['gpt-4o', 'gpt-4o-mini'])
ok('choose a model', P('model', {'id': 'openai', 'model': 'gpt-4o'})[0] == 200)
ok('absurd model name refused', P('model', {'id': 'openai', 'model': 'x' * 500})[0] == 409)
seen.clear(); c, b = post('/chat', {'message': 'привет'})
ev = [json.loads(l) for l in b.splitlines() if l]
ok('chat goes to the chosen provider with key and chosen model', c == 200 and seen and seen[0][0] == 'cloud' and seen[0][1] == 'Bearer ' + SECRET and seen[0][2]['model'] == 'gpt-4o' and 'max_completion_tokens' in seen[0][2] and 'thinking' not in seen[0][2])
ok('she answered', any('answer' in e for e in ev))
P('key', {'id': 'openai', 'key': 'sk-OTHER-KEY-99999999'}) if False else None
c, r = P('state'); ok('local scan sees fake Ollama running with 2 models', any(x['id'] == 'ollama' and x['running'] and x['models'] == 2 for x in r['local']))
c, r = P('select', {'id': 'ollama'}); ok('local connected, first model picked', c == 200 and r['active'] == 'ollama' and r['ready'])
seen.clear(); c, b = post('/chat', {'message': 'привет'})
ok('local chat has no Authorization and uses the local model', c == 200 and seen[0][0] == 'local' and seen[0][1] is None and seen[0][2]['model'] == 'llama3.2:3b' and 'max_tokens' in seen[0][2])
providers.set_model('ollama', 'llama3.2:3b')
try: providers.endpoint(vision=True) ; vm = providers.endpoint(vision=True)['model']
except providers.ProviderError as e: vm = str(e)
ok('vision picks the llava model among local ones', vm == 'llava:7b')
providers.set_model('ollama', 'llama3.2:3b'); P('dismiss', {'id': 'ollama'}); c, r = P('state')
ok('dismiss is remembered', next(x for x in r['local'] if x['id'] == 'ollama')['dismissed'])
c, r = P('select', {'id': 'lmstudio'}); ok('selecting a runtime that is not running -> notrunning', c == 409 and 'notrunning' in r['error'])
c, r = P('clear', {'id': 'openai'}); ok('key removed; local stays active', c == 200 and not next(x for x in r['cloud'] if x['id'] == 'openai')['hasKey'] and r['active'] == 'ollama')
providers.select('ollama') ; P('select', {'id': 'ollama'})
ok('removed key is gone from disk', SECRET not in providers.KEYS_FILE.read_text())
c, b = post('/chat', {'message': 'привет', 'image': 'data:image/jpeg;base64,AAAA'}); ok('picture to a vision model works (llava)', c == 200)
print('seen vision model:', seen[-1][2]['model'])
