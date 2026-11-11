"""Meaning-based recall for Luna's memory: which stored facts fit what is being talked about right now.

The facts themselves stay in memory.json (readable, backed up, one place of truth). This module only adds a *similarity* between the text being
talked about and each fact, so that «собаку» finds «у него живёт собака Мишка», a typo or another case still matches, and (when a real embedding
model is available) so does a synonym.

Two layers, the second optional:
  1. an offline word-form match: every content word of the query looks for a form of itself among the words of the fact (same start, or
     similar by letter 3-grams: «собаку» ~ «собака», «японию» ~ «Японию», a typo ~ the word). No model, no network, no dependency;
     understands word forms and typos, not synonyms.
  2. an embedder (set_embedder): a function text -> list of floats from a real embedding model, for example Ollama's /api/embeddings
     (ollama_embedder). Its vectors are cached in a small SQLite file next to the data, keyed by the model and the text hash, so a fact is
     embedded once. If the embedder fails, the offline word-form match is used: recall never breaks.

Pure standard library."""
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import urllib.request

_WORD = re.compile(r'\w+', re.U)
_CJK = re.compile(r'[぀-ヿ一-鿿가-힯]+')
LOCK = threading.RLock()

_embedder = None      # (name, callable) or None
_db_path = None       # where the vector cache lives (None = no cache, memory only)
_mem_cache = {}       # (model, text) -> vector, bounded
_MEM_MAX = 2000

# words that say nothing about the topic (they would make every sentence look alike)
STOP = set('''это этот эта эти что как так для при про над под без или если когда потом тоже уже ещё еще был была были быть есть нет
  его её ему ему они она оно мне меня тебе тебя ты вы мы он нас вас свою свой мой моя моё мои твой твоя какой какая какие кто где
  очень просто только можно надо нужно хочу хочет хотел расскажи скажи давай ладно ну вот
  the and for with that this have has are was were you your his her its our their what when where how not but from about into
  just very can could would should will shall'''.split())


def words(text):
    """The content words of a text: lower-case, 3+ letters, not in STOP; CJK runs are cut into letter pairs."""
    low = str(text).lower()
    out = []
    for run in _CJK.findall(low):
        out += [run[i:i + 2] for i in range(max(1, len(run) - 1))]
    out += [w for w in _WORD.findall(_CJK.sub(' ', low)) if len(w) >= 3 and w not in STOP and not w.isdigit()]
    return out


def _grams(word):
    padded = '^' + word + '$'
    return {padded[i:i + 3] for i in range(len(padded) - 2)}


def word_similarity(a, b):
    """0..1: how much two words look like forms of one word. Same word 1; a long shared start («собаку» ~ «собака», «японию» ~ «Японию»)
    0.9; a typo or another ending by letter 3-grams (Dice) when that is at least 0.5; otherwise 0."""
    if a == b:
        return 1.0
    prefix = 0
    for x, y in zip(a, b):
        if x != y:
            break
        prefix += 1
    if prefix >= 4 and prefix >= 0.6 * min(len(a), len(b)):
        return 0.9
    ga, gb = _grams(a), _grams(b)
    dice = 2 * len(ga & gb) / (len(ga) + len(gb))
    return dice if dice >= 0.5 else 0.0


def fuzzy_similarity(query_words, item_words):
    """0..1: the share of the query's content words (longer words count more) that have a form of themselves in the item."""
    if not query_words or not item_words:
        return 0.0
    got = total = 0.0
    for q in query_words:
        weight = min(len(q), 8)
        total += weight
        got += weight * max(word_similarity(q, w) for w in item_words)
    return got / total


def cosine(a, b):
    """Cosine of two unit vectors (0 for different lengths or empty vectors)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


# --- the optional real embedding model ---------------------------------------------------------------------------------------------------
def set_embedder(name, function):
    """Use `function(text) -> list[float]` (a real embedding model) named `name`; None switches back to the offline vectors."""
    global _embedder
    with LOCK:
        _embedder = (name, function) if function else None
        _mem_cache.clear()


def configure_cache(path):
    """Keep embedded vectors in an SQLite file (None = memory only). Safe to call again."""
    global _db_path
    with LOCK:
        _db_path = str(path) if path else None
        if _db_path:
            try:
                with _connect() as db:
                    db.execute('CREATE TABLE IF NOT EXISTS vec (model TEXT NOT NULL, h TEXT NOT NULL, data TEXT NOT NULL, ts REAL NOT NULL, PRIMARY KEY (model, h))')
            except (sqlite3.Error, OSError):
                _db_path = None


def _connect():
    return sqlite3.connect(_db_path, timeout=5)


def _text_key(text):
    return hashlib.sha256(str(text).encode('utf-8')).hexdigest()[:32]


def _cached(model, text):
    key = (model, text)
    if key in _mem_cache:
        return _mem_cache[key]
    if _db_path:
        try:
            with _connect() as db:
                row = db.execute('SELECT data FROM vec WHERE model=? AND h=?', (model, _text_key(text))).fetchone()
            if row:
                vec = json.loads(row[0])
                _mem_cache[key] = vec
                return vec
        except (sqlite3.Error, ValueError, OSError):
            pass
    return None


def _store(model, text, vec):
    if len(_mem_cache) >= _MEM_MAX:
        _mem_cache.clear()
    _mem_cache[(model, text)] = vec
    if _db_path:
        try:
            with _connect() as db:
                db.execute('INSERT OR REPLACE INTO vec (model, h, data, ts) VALUES (?, ?, ?, ?)', (model, _text_key(text), json.dumps(vec), time.time()))
                db.execute('DELETE FROM vec WHERE h IN (SELECT h FROM vec ORDER BY ts DESC LIMIT -1 OFFSET 5000)')   # the cache stays small
        except (sqlite3.Error, OSError):
            pass


def _unit(vec):
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def vector(text):
    """The embedding of a text (cached), or None when there is no embedding model or it failed. Returns (name, vector) or (None, None)."""
    text = str(text)[:2000]
    with LOCK:
        emb = _embedder
    if not emb:
        return None, None
    name, function = emb
    with LOCK:
        hit = _cached(name, text)
    if hit is not None:
        return name, hit
    try:
        vec = [float(x) for x in function(text)]
        if vec and all(math.isfinite(x) for x in vec):
            vec = _unit(vec)
            with LOCK:
                _store(name, text, vec)
            return name, vec
    except Exception:   # a model that is down must never break recall
        pass
    return None, None


def similarities(query, items):
    """-> [float per item]: how close each fact is to the query in meaning, 0..1 (0 = nothing in common).
    With an embedding model: cosine of the embeddings (rescaled so that unrelated texts give 0). Without one, or if it fails for any of the
    texts: the offline word-form match (fuzzy_similarity)."""
    items = [str(i) for i in items]
    name, q = vector(query)
    if q is not None:
        vecs = [vector(i) for i in items]
        if all(n == name for n, _ in vecs):
            floor = 0.35   # below this two texts only share the ordinary words of the language
            return [max(0.0, (cosine(q, v) - floor) / (1 - floor)) for _, v in vecs]
    qw = words(query)
    return [fuzzy_similarity(qw, words(i)) for i in items]


def ollama_embedder(base='http://127.0.0.1:11434', model='nomic-embed-text', timeout=8):
    """Embeddings from a local Ollama (ollama pull nomic-embed-text). Only a loopback address is accepted: memory never leaves the computer."""
    if not re.match(r'^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?/?$', base):
        raise ValueError('only a local address is allowed')

    def embed(text):
        body = json.dumps({'model': model, 'prompt': text}).encode('utf-8')
        request = urllib.request.Request(base.rstrip('/') + '/api/embeddings', data=body, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=timeout) as response:   # noqa: S310 - loopback only, checked above
            return json.loads(response.read(2_000_000).decode('utf-8'))['embedding']
    return 'ollama:' + model, embed
