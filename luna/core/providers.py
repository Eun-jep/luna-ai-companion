"""Which neural network she thinks with: chosen in the settings, never typed into a console.
Cloud services (Z.ai, OpenAI, Anthropic, Google Gemini, OpenRouter) need a key: it is asked for in a dialog, checked against
the service, and stored encrypted for this Windows user (DPAPI) in keys.dat, so the next launch is already connected.
Local runtimes (Ollama, LM Studio, Jan, llama.cpp server) are found by looking at the loopback ports and install folders.
Everything speaks the OpenAI chat-completions protocol. The page never gets a key back, only the last four characters.
Errors travel as codes ('prov:badkey|detail') that the page translates into the interface language."""
from luna import paths
import base64
import ctypes
import json
import os
import re
import shutil
import threading
import urllib.error
import urllib.request
from ctypes import wintypes

ROOT = paths.ROOT
CHOICE_FILE = paths.data_file('providers.json')   # which one is active and which model: no secrets
KEYS_FILE = paths.data_file('keys.dat')         # the keys, encrypted for this Windows user
_lock = threading.RLock()

CLOUD = {
    'zai': {'name': 'Z.ai (GLM)', 'base': 'https://api.z.ai/api/paas/v4', 'default': 'glm-4.5-flash', 'vision': 'glm-4.6v-flash',
            'models': ['glm-4.5-flash', 'glm-4.5-air', 'glm-4.6'], 'free': ['glm-4.5-flash', 'glm-4.6v-flash'], 'list': False,
            'extra': {'thinking': {'type': 'disabled'}}, 'tokens': 'max_tokens', 'url': 'https://z.ai/manage-apikey/apikey-list'},
    'openai': {'name': 'OpenAI', 'base': 'https://api.openai.com/v1', 'default': 'gpt-4o-mini', 'models': ['gpt-4o-mini', 'gpt-4o'],
               'list': True, 'keep': r'^(gpt|chatgpt|o\d)', 'tokens': 'max_completion_tokens', 'url': 'https://platform.openai.com/api-keys'},
    'anthropic': {'name': 'Anthropic (Claude)', 'base': 'https://api.anthropic.com/v1', 'default': 'claude-haiku-5-5',
                  'models': ['claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5'], 'list': True, 'keep': r'^claude',
                  'tokens': 'max_tokens', 'url': 'https://console.anthropic.com/settings/keys'},
    'gemini': {'name': 'Google Gemini', 'base': 'https://generativelanguage.googleapis.com/v1beta/openai', 'default': 'gemini-2.0-flash',
               'models': ['gemini-2.0-flash'], 'list': True, 'keep': r'^gemini', 'tokens': 'max_tokens', 'url': 'https://aistudio.google.com/app/apikey'},
    'openrouter': {'name': 'OpenRouter', 'base': 'https://openrouter.ai/api/v1', 'default': 'meta-llama/llama-3.3-70b-instruct:free',
                   'models': ['meta-llama/llama-3.3-70b-instruct:free'], 'list': True, 'keep': r'', 'tokens': 'max_tokens', 'url': 'https://openrouter.ai/keys'},
}
LOCAL = {
    'ollama': {'name': 'Ollama', 'base': 'http://127.0.0.1:11434/v1', 'tags': 'http://127.0.0.1:11434/api/tags',
               'installed': ['%LOCALAPPDATA%\\Programs\\Ollama\\ollama.exe', '%ProgramFiles%\\Ollama\\ollama.exe'], 'which': 'ollama'},
    'lmstudio': {'name': 'LM Studio', 'base': 'http://127.0.0.1:1234/v1', 'installed': ['%LOCALAPPDATA%\\LM-Studio', '%USERPROFILE%\\.lmstudio', '%ProgramFiles%\\LM Studio']},
    'jan': {'name': 'Jan', 'base': 'http://127.0.0.1:1337/v1', 'installed': ['%LOCALAPPDATA%\\Programs\\Jan', '%APPDATA%\\Jan']},
    'llamacpp': {'name': 'llama.cpp server', 'base': 'http://127.0.0.1:8080/v1', 'installed': [], 'which': 'llama-server'},
}
# Cloud services that have an embeddings endpoint in the OpenAI protocol (meaning-based memory and tone without a local model).
# dims: the vector is cut to this many numbers and renormalised (both models are trained for that), so the cache stays small.
EMBED = {
    'gemini': {'model': 'gemini-embedding-001', 'dims': 768},
    'openai': {'model': 'text-embedding-3-small', 'dims': 512},
}
VISION_HINT = re.compile(r'llava|vision|\bvl\b|-vl|vl:|gemma3|minicpm-v|moondream|bakllava|pixtral|qwen2\.5vl|qwen2-vl|internvl', re.I)

_choice = {'active': '', 'model': {}, 'dismissed': [], 'embed': False}
_keys = {}                     # id -> key, in memory only after decryption
_models_cache = {}             # id -> [model ids]


class ProviderError(RuntimeError):
    """message = 'prov:<code>|<detail>': the page translates the code."""

    def __init__(self, code, detail=''):
        super().__init__('prov:' + code + ('|' + detail if detail else ''))
        self.code = code


# ---- encrypted storage (Windows DPAPI: only this Windows user on this machine can decrypt) ----

class _Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]


def _dpapi(data, protect):
    buf = ctypes.create_string_buffer(data, len(data))
    src, out = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), _Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError('dpapi')
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _seal(text):
    raw = text.encode('utf-8')
    try:
        return 'dpapi:' + base64.b64encode(_dpapi(raw, True)).decode()
    except (OSError, AttributeError):   # not Windows: the file at least stays out of git and readable by this user only
        return 'plain:' + base64.b64encode(raw).decode()


def _unseal(blob):
    kind, _, body = blob.partition(':')
    raw = base64.b64decode(body)
    return (_dpapi(raw, False) if kind == 'dpapi' else raw).decode('utf-8')


def _save_keys():
    sealed = {k: _seal(v) for k, v in _keys.items()}
    tmp = KEYS_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(sealed), encoding='utf-8')
    tmp.replace(KEYS_FILE)
    try:
        os.chmod(KEYS_FILE, 0o600)
    except OSError:
        pass


def _save_choice():
    tmp = CHOICE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(_choice, ensure_ascii=False), encoding='utf-8')
    tmp.replace(CHOICE_FILE)


def load():
    """Read what was saved. A key in the ZAI_API_KEY variable (the old way) is adopted once if nothing is stored."""
    with _lock:
        try:
            for k, blob in json.loads(KEYS_FILE.read_text(encoding='utf-8')).items():
                try:
                    if k in CLOUD:
                        _keys[k] = _unseal(blob)
                except (OSError, ValueError):
                    pass   # a key sealed by another Windows user: ask again
        except (OSError, ValueError):
            pass
        try:
            data = json.loads(CHOICE_FILE.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                _choice['active'] = data.get('active') if data.get('active') in {**CLOUD, **LOCAL} else ''
                _choice['model'] = {k: v for k, v in (data.get('model') or {}).items() if isinstance(v, str)}
                _choice['dismissed'] = [x for x in data.get('dismissed') or [] if x in LOCAL]
                _choice['embed'] = data.get('embed') is True
        except (OSError, ValueError):
            pass
        env = os.environ.get('ZAI_API_KEY', '').strip()
        if env and 'zai' not in _keys:
            _keys['zai'] = env
            try:
                _save_keys()
            except OSError:
                pass
            if not _choice['active']:
                _choice['active'] = 'zai'
        if _choice['active'] in CLOUD and _choice['active'] not in _keys:
            _choice['active'] = ''


def redact(text):
    for k in _keys.values():
        if k and k in text:
            text = text.replace(k, '[KEY REMOVED]')
    return text


# ---- talking to a service ----

def _call(url, key=None, body=None, timeout=15):
    headers = {'Content-Type': 'application/json', 'User-Agent': 'LunaCompanion/1.0'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8') if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read(4000000))
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            data = json.loads(exc.read(8000))
            msg = data.get('message') or data.get('detail') or data.get('error') or ''
            detail = (msg.get('message', '') if isinstance(msg, dict) else str(msg))[:300]
        except (ValueError, AttributeError):
            pass
        code = {401: 'badkey', 403: 'badkey', 402: 'billing', 429: 'limit', 404: 'model', 400: 'model'}.get(exc.code, 'http')
        if key:
            detail = detail.replace(key, '[KEY REMOVED]')   # a service may echo the key it just refused
        raise ProviderError(code, redact(detail)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderError('network') from None
    except ValueError:
        raise ProviderError('http') from None


def _local_models(pid):
    spec = LOCAL[pid]
    if spec.get('tags'):
        data = _call(spec['tags'], timeout=1.5)
        return [m['name'] for m in data.get('models', []) if isinstance(m, dict) and m.get('name')]
    data = _call(spec['base'] + '/models', timeout=1.5)
    return [m['id'] for m in data.get('data', []) if isinstance(m, dict) and m.get('id')]


def _cloud_models(pid, key):
    spec = CLOUD[pid]
    if not spec['list']:
        return list(spec['models'])
    data = _call(spec['base'] + '/models', key)
    items = data.get('data') or data.get('models') or []
    ids = [str(m.get('id') or m.get('name') or '').replace('models/', '') for m in items if isinstance(m, dict)]
    keep = re.compile(spec.get('keep') or '')
    ids = sorted({i for i in ids if i and keep.search(i) and not re.search(r'embed|whisper|tts|dall|moderation|image|audio|realtime|transcribe', i, re.I)})
    return ids or list(spec['models'])


def models(pid):
    """Models to choose from for a provider (cached). ProviderError when the service cannot be reached."""
    with _lock:
        if pid in LOCAL:
            ids = _local_models(pid)
        elif pid in CLOUD and pid in _keys:
            try:
                ids = _cloud_models(pid, _keys[pid])
            except ProviderError as exc:
                if exc.code in ('network', 'badkey'):
                    raise
                ids = list(CLOUD[pid]['models'])
        else:
            raise ProviderError('nokey')
        current = _choice['model'].get(pid)
        if current and current not in ids:
            ids = [current] + ids
        _models_cache[pid] = ids
        return ids


def check_key(pid, key):
    """Does the service accept this key? Raises ProviderError('badkey'...) if not; returns a warning code or ''."""
    spec = CLOUD[pid]
    if spec['list']:
        _cloud_models(pid, key)
        return ''
    try:   # no model list at this service: one tiny request
        _call(spec['base'] + '/chat/completions', key, {'model': spec['default'], 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 1, **spec.get('extra', {})})
    except ProviderError as exc:
        if exc.code == 'billing':
            return 'billing'   # the key is real, the account just has no balance
        if exc.code in ('limit', 'model'):
            return ''
        raise
    return ''


def set_key(pid, key):
    """Check the key, store it encrypted, make this provider the active one."""
    if pid not in CLOUD:
        raise ProviderError('unknown')
    key = (key or '').strip()
    if not 8 <= len(key) <= 400 or re.search(r'\s', key):
        raise ProviderError('badkey')
    warn = check_key(pid, key)
    with _lock:
        _keys[pid] = key
        _save_keys()
        _choice['active'] = pid
        _choice['model'].setdefault(pid, CLOUD[pid]['default'])
        _save_choice()
    return warn


def clear_key(pid):
    with _lock:
        _keys.pop(pid, None)
        _models_cache.pop(pid, None)
        if _choice['active'] == pid:
            _choice['active'] = ''
        _save_keys()
        _save_choice()


def select(pid):
    """Make a provider active. 'nokey' for a cloud service without a key, 'notrunning' for a local one that does not answer."""
    with _lock:
        if pid in CLOUD:
            if pid not in _keys:
                raise ProviderError('nokey')
            _choice['model'].setdefault(pid, CLOUD[pid]['default'])
        elif pid in LOCAL:
            try:
                ids = _local_models(pid)
            except ProviderError:
                raise ProviderError('notrunning', LOCAL[pid]['name']) from None
            if not ids:
                raise ProviderError('nomodels')
            if _choice['model'].get(pid) not in ids:
                _choice['model'][pid] = ids[0]
            if pid in _choice['dismissed']:
                _choice['dismissed'].remove(pid)
        else:
            raise ProviderError('unknown')
        _choice['active'] = pid
        _save_choice()


def set_model(pid, model):
    with _lock:
        if pid not in {**CLOUD, **LOCAL} or not isinstance(model, str) or not 1 <= len(model) <= 200:
            raise ProviderError('unknown')
        _choice['model'][pid] = model
        _save_choice()


def dismiss(pid):
    with _lock:
        if pid in LOCAL and pid not in _choice['dismissed']:
            _choice['dismissed'].append(pid)
            _save_choice()


def _installed(spec):
    if spec.get('which') and shutil.which(spec['which']):
        return True
    return any(os.path.exists(os.path.expandvars(p)) for p in spec.get('installed', []))


def scan_local():
    """Look for local runtimes: [{id, name, running, installed, models}]."""
    out = []
    for pid, spec in LOCAL.items():
        try:
            ids = _local_models(pid)
            running = True
        except ProviderError:
            ids, running = [], False
        out.append({'id': pid, 'name': spec['name'], 'running': running, 'installed': running or _installed(spec), 'models': len(ids),
                    'dismissed': pid in _choice['dismissed']})
    return out


def state():
    """What the settings page shows. No key ever leaves this module, only its last four characters."""
    local = scan_local()
    cloud = [{'id': pid, 'name': spec['name'], 'hasKey': pid in _keys, 'hint': _keys[pid][-4:] if pid in _keys else '',
              'model': _choice['model'].get(pid, spec['default']), 'url': spec['url']} for pid, spec in CLOUD.items()]
    for item in local:
        item['model'] = _choice['model'].get(item['id'], '')
    return {'active': _choice['active'], 'ready': ready(), 'cloud': cloud, 'local': local,
            'embed': {'on': _choice['embed'], 'can': embed_possible(), 'name': (CLOUD.get(_choice['active']) or {}).get('name', '')}}


# ---- what app.py needs for one request ----

def ready():
    a = _choice['active']
    return bool(a) and (a in LOCAL or a in _keys)


def vision_model():
    a = _choice['active']
    if a in CLOUD:
        return CLOUD[a].get('vision') or _choice['model'].get(a) or CLOUD[a]['default']
    chosen = _choice['model'].get(a, '')
    if VISION_HINT.search(chosen):
        return chosen
    try:
        for m in _local_models(a):
            if VISION_HINT.search(m):
                return m
    except ProviderError:
        pass
    return None


def endpoint(vision=False, model=None):
    """{url, headers, model, extra, tokens} for the active provider, or ProviderError."""
    with _lock:
        a = _choice['active']
        if not ready():
            raise ProviderError('nokey')
        if vision:
            chosen = vision_model()
            if not chosen:
                raise ProviderError('novision')
        else:
            chosen = model or _choice['model'].get(a) or (CLOUD[a]['default'] if a in CLOUD else '')
            if not chosen:
                raise ProviderError('nomodels')
        spec = CLOUD.get(a) or LOCAL[a]
        headers = {'Content-Type': 'application/json'}
        if a in CLOUD:
            headers['Authorization'] = 'Bearer ' + _keys[a]
        return {'url': spec['base'] + '/chat/completions', 'headers': headers, 'model': chosen, 'extra': spec.get('extra', {}),
                'tokens': spec.get('tokens', 'max_tokens'), 'name': spec['name']}


# ---- meaning-based memory and tone through the active cloud service (opt-in) ----

def embed_possible():
    """Can the active service embed texts? (only a cloud one with a key and an embeddings endpoint)"""
    return _choice['active'] in EMBED and _choice['active'] in _keys


def set_embed(on):
    with _lock:
        _choice['embed'] = bool(on)
        _save_choice()


def embed_spec():
    """'cloud:<id>' when the user turned this on and the active service can do it, else ''."""
    return 'cloud:' + _choice['active'] if _choice['embed'] and embed_possible() else ''


def embedder(pid=None):
    """-> (name, embed(text), embed_many(texts)) for memory_store.set_embedder. The key is read at call time and never leaves this module."""
    pid = pid or _choice['active']
    if pid not in EMBED:
        raise ProviderError('unknown')
    spec, base = EMBED[pid], CLOUD[pid]['base'] + '/embeddings'

    def many(texts):
        key = _keys.get(pid)
        if not key:
            raise ProviderError('nokey')
        data = _call(base, key, {'model': spec['model'], 'input': list(texts)}, timeout=10)
        rows = sorted((r for r in data['data'] if isinstance(r, dict)), key=lambda r: r.get('index', 0))
        return [r['embedding'][:spec['dims']] for r in rows]

    def one(text):
        return many([text])[0]
    return 'cloud:%s:%s' % (pid, spec['model']), one, many
