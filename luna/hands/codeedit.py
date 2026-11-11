"""Her hands on code (part 6): she proposes changes to a code file the creator already showed her, the creator sees the exact
diff and presses Apply, and only then the file changes. Every change keeps a backup, is written to the journal and can be taken
back there. What she cannot do: touch a file she was not shown, create, rename or delete files, run anything, or write anything
that is not an exact replacement of text that is really in the file (a replacement that does not match once is refused)."""
import difflib
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path

from luna.dev import devtools
from luna import paths

BACKUPS = paths.data_file('edit_backups')
KEEP_BACKUPS = 60
TTL, MAX_PENDING, MAX_EDITS = 600, 10, 12
MAX_FIND, MAX_REPLACE, MAX_SPEC = 6000, 12000, 60000
PENDING = {}                     # token -> a validated change waiting for the creator's press (single use)
_stamps = []
_lock = threading.Lock()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _granted(name):
    """The path of a file the creator showed her (by the name she saw it under), or None."""
    entry = devtools.GRANTED.get(str(name).strip().lower())
    if entry and time.time() - entry['t'] <= devtools.GRANT_TTL:
        return entry['path']
    return None


def parse(src):
    """The JSON of a ```lunaedit block -> (file name, [(find, replace)]). ValueError('bad') when it is not exactly that shape."""
    try:
        spec = json.loads(src[:MAX_SPEC])
    except ValueError:
        raise ValueError('bad')
    if not isinstance(spec, dict) or not isinstance(spec.get('file'), str) or not isinstance(spec.get('edits'), list):
        raise ValueError('bad')
    edits = []
    for e in spec['edits']:
        if not isinstance(e, dict) or not isinstance(e.get('find'), str) or not isinstance(e.get('replace'), str):
            raise ValueError('bad')
        if not e['find'].strip() or len(e['find']) > MAX_FIND or len(e['replace']) > MAX_REPLACE:
            raise ValueError('bad')
        edits.append((e['find'], e['replace']))
    if not 1 <= len(edits) <= MAX_EDITS:
        raise ValueError('bad')
    return spec['file'], edits


def _load(path):
    """(text with \\n newlines, had BOM, uses CRLF, raw bytes) of an allowed code file. ValueError('file'|'encoding')."""
    low = os.path.basename(path).lower()
    if (os.path.splitext(low)[1] not in devtools.CODE_EXT or devtools.SECRET_RE.search(low) or not os.path.isfile(path)
            or os.path.getsize(path) > devtools.MAX_READ_BYTES):
        raise ValueError('file')
    raw = Path(path).read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    try:
        text = raw[3 if bom else 0:].decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError('encoding')
    crlf = '\r\n' in text
    return text.replace('\r\n', '\n'), bom, crlf, raw


def _encode(text, bom, crlf):
    if crlf:
        text = text.replace('\n', '\r\n')
    return (b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8')


def propose(src):
    """Validate a change against the real file and return the plate {token, file, edits, added, removed, diff}.
    ValueError(code): bad | nofile (not shown to her) | file | encoding | nomatch | multi | same."""
    name, edits = parse(src)
    path = _granted(name)
    if not path:
        raise ValueError('nofile')
    text, bom, crlf, raw = _load(path)
    new = text
    for find, replace in edits:
        find, replace = find.replace('\r\n', '\n'), replace.replace('\r\n', '\n')
        hits = new.count(find)
        if hits == 0:
            raise ValueError('nomatch')
        if hits > 1:
            raise ValueError('multi')
        new = new.replace(find, replace, 1)
    if new == text:
        raise ValueError('same')
    lines = list(difflib.unified_diff(text.splitlines(), new.splitlines(), 'before', 'after', lineterm='', n=3))
    added = sum(1 for l in lines if l.startswith('+') and not l.startswith('+++'))
    removed = sum(1 for l in lines if l.startswith('-') and not l.startswith('---'))
    diff = '\n'.join(lines)
    now = time.time()
    with _lock:
        for k in [k for k, v in PENDING.items() if now - v['t'] > TTL]:
            del PENDING[k]
        if len(PENDING) >= MAX_PENDING:
            raise ValueError('bad')
        token = secrets.token_hex(8)
        PENDING[token] = {'t': now, 'path': path, 'name': os.path.basename(path), 'before': _sha(raw), 'data': _encode(new, bom, crlf)}
    return {'token': token, 'file': os.path.basename(path), 'edits': len(edits), 'added': added, 'removed': removed,
            'diff': diff[:20000], 'cut': len(diff) > 20000}


def _prune():
    try:
        files = sorted(BACKUPS.iterdir(), key=lambda p: p.stat().st_mtime)
        for p in files[:-KEEP_BACKUPS]:
            p.unlink()
    except OSError:
        pass


def _atomic(path, data):
    tmp = Path(str(path) + '.luna.tmp')
    tmp.write_bytes(data)
    os.replace(tmp, path)


def apply(token):
    """The creator pressed Apply. Returns {'name','added','removed','backup','after'} for the journal.
    PermissionError('token'), RuntimeError('rate'|'changed'|'write')."""
    with _lock:
        entry = PENDING.pop(token, None) if isinstance(token, str) else None
        now = time.time()
        if not entry or now - entry['t'] > TTL:
            raise PermissionError('token')
        _stamps[:] = [s for s in _stamps if now - s < 60]
        if len(_stamps) >= 10:
            raise RuntimeError('rate')
        _stamps.append(now)
    path = entry['path']
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise RuntimeError('write')
    if _sha(raw) != entry['before']:   # she proposed against another version of the file
        raise RuntimeError('changed')
    try:
        BACKUPS.mkdir(parents=True, exist_ok=True)
        backup = BACKUPS / ('%d_%s' % (int(now), entry['name']))
        backup.write_bytes(raw)
        _atomic(path, entry['data'])
    except OSError:
        raise RuntimeError('write')
    _prune()
    return {'name': entry['name'], 'path': path, 'backup': str(backup), 'after': _sha(entry['data'])}


def restore(path, backup, after):
    """Put the backup back, but only if the file is still exactly what she wrote. RuntimeError('changed'|'write')."""
    backup = Path(backup)
    if BACKUPS.resolve() not in backup.resolve().parents or not backup.is_file():
        raise RuntimeError('write')
    try:
        if _sha(Path(path).read_bytes()) != after:
            raise RuntimeError('changed')
        _atomic(path, backup.read_bytes())
    except OSError:
        raise RuntimeError('write')
