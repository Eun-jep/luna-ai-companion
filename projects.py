"""Her hands on new projects: she proposes a set of NEW files (a project), the creator sees every file and presses Apply, and
only then the files appear, inside one sandbox folder (Documents\\Luna\\Projects) and nowhere else. What she cannot do: write
outside the sandbox, overwrite or delete an existing file, create programs or scripts that start by a double click, or write
secret files. Every project is written to the journal with a manifest, so the Journal can take it back (only while the files
are still exactly what she wrote)."""
import hashlib
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

import devtools

HERE = Path(__file__).resolve().parent
MANIFESTS = HERE / 'project_manifests'
ROOT = None                      # tests point this elsewhere
TTL, MAX_PENDING = 600, 6
MAX_SPEC, MAX_FILES, MAX_FILE, MAX_TOTAL, MAX_DEPTH = 400000, 40, 120000, 600000, 6
FORBIDDEN_EXT = {'.bat', '.cmd', '.ps1', '.vbs', '.lnk', '.exe', '.dll', '.msi', '.scr', '.reg', '.com', '.jar', '.js.lnk'}
ALLOWED_EXT = (devtools.CODE_EXT - FORBIDDEN_EXT) | {'.csv', '.svg', '.scss', '.vue', '.svelte', '.pyi', '.gradle', '.mjs', '.cjs'}
ALLOWED_NAMES = {'.gitignore', 'readme', 'license', 'makefile', 'dockerfile', 'requirements.txt'}
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *('COM%d' % i for i in range(1, 10)), *('LPT%d' % i for i in range(1, 10))}
BAD_CHARS = re.compile(r'[<>:"|?*\\\x00-\x1f]')
PENDING = {}                     # token -> a validated project waiting for the creator's press (single use)
_stamps = []
_lock = threading.Lock()


def root():
    if ROOT:
        return Path(ROOT)
    docs = Path.home() / 'Documents'
    return (docs if docs.is_dir() else Path.home()) / 'Luna' / 'Projects'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _part_ok(part):
    stem = part.split('.')[0].upper()
    return bool(part) and part not in ('.', '..') and not BAD_CHARS.search(part) and part == part.rstrip('. ') and stem not in RESERVED


def clean_name(name):
    """A safe folder name for the project: letters, digits, spaces, dashes. ValueError('bad') if nothing is left."""
    name = re.sub(r'[^\w \-]', '', str(name), flags=re.U).strip()[:40].strip()
    if not name or name.upper() in RESERVED:
        raise ValueError('bad')
    return name


def _file_path(rel):
    """The normalised relative path with / separators; ValueError('path') for anything that could leave the project or is risky."""
    if not isinstance(rel, str) or not rel or len(rel) > 120 or rel.startswith('/') or '\\' in rel or re.match(r'^[A-Za-z]:', rel):
        raise ValueError('path')
    parts = rel.split('/')
    if len(parts) > MAX_DEPTH or not all(_part_ok(p) for p in parts):
        raise ValueError('path')
    if any(p.startswith('.') for p in parts[:-1]) or (parts[-1].startswith('.') and parts[-1].lower() not in ALLOWED_NAMES):
        raise ValueError('path')
    low = parts[-1].lower()
    ext = os.path.splitext(low)[1]
    if devtools.SECRET_RE.search(low) or any(devtools.SECRET_RE.search(p.lower()) for p in parts[:-1]):
        raise ValueError('secret')
    if low not in ALLOWED_NAMES and ext not in ALLOWED_EXT:
        raise ValueError('ext')
    return '/'.join(parts)


def parse(src):
    """The JSON of a ```lunaproject block -> (project name or folder, workspace name or '', [(relative path, text)]).
    ValueError(code): bad | path | secret | ext | big | nows (a folder the creator did not allow)."""
    try:
        spec = json.loads(src[:MAX_SPEC])
    except ValueError:
        raise ValueError('bad')
    if not isinstance(spec, dict) or not isinstance(spec.get('files'), list):
        raise ValueError('bad')
    ws = spec.get('workspace')
    if ws:
        if not isinstance(ws, str) or not find_workspace(ws):
            raise ValueError('nows')
        name = ws.strip()
    else:
        ws, name = '', clean_name(spec.get('project', ''))
    files, seen, total = [], set(), 0
    for f in spec['files']:
        if not isinstance(f, dict) or not isinstance(f.get('text'), str):
            raise ValueError('bad')
        rel = _file_path(f.get('path'))
        if rel.lower() in seen:
            raise ValueError('path')
        seen.add(rel.lower())
        text = f['text'].replace('\r\n', '\n')
        if len(text) > MAX_FILE:
            raise ValueError('big')
        total += len(text)
        files.append((rel, text))
    if not 1 <= len(files) <= MAX_FILES:
        raise ValueError('bad')
    if total > MAX_TOTAL:
        raise ValueError('big')
    return name, ws, files


# ---- folders the creator allowed (off until he adds one): she may add NEW files to a project that lives there ----
WS_FILE = HERE / 'workspaces.json'
WS_LIMIT = 8
SYSTEM_DIRS = ('windows', 'program files', 'program files (x86)', 'programdata', 'appdata', '$recycle.bin', 'system volume information')


def workspaces():
    try:
        data = json.loads(WS_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [w for w in data if isinstance(w, dict) and isinstance(w.get('name'), str) and isinstance(w.get('path'), str)][:WS_LIMIT]


def find_workspace(name):
    name = str(name).strip().lower()
    return next((w for w in workspaces() if w['name'].lower() == name and os.path.isdir(w['path'])), None)


def _save_workspaces(items):
    tmp = WS_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(WS_FILE)


def add_workspace(path):
    """The creator added a folder. ValueError(code): bad | notdir | unsafe | dup | limit."""
    if not isinstance(path, str) or not path.strip() or len(path) > 300 or '\0' in path:
        raise ValueError('bad')
    p = Path(path.strip().strip('"'))
    try:
        if not p.is_dir():
            raise ValueError('notdir')
        real = p.resolve()
    except OSError:
        raise ValueError('notdir')
    parts = [x.lower() for x in real.parts]
    home = Path.home().resolve()
    protected = {home, home / 'Documents', home / 'Desktop', home / 'Downloads', home / 'Pictures', home / 'Music', home / 'Videos'}
    if (len(parts) < 3 or real in protected or any(x in SYSTEM_DIRS for x in parts) or HERE == real or HERE in real.parents or real in HERE.parents
            or MANIFESTS.resolve() == real):
        raise ValueError('unsafe')
    name = real.name
    with _lock:
        items = workspaces()
        if any(w['name'].lower() == name.lower() or w['path'].lower() == str(real).lower() for w in items):
            raise ValueError('dup')
        if len(items) >= WS_LIMIT:
            raise ValueError('limit')
        items.append({'name': name, 'path': str(real)})
        _save_workspaces(items)
    return items[-1]


def remove_workspace(name):
    with _lock:
        items = workspaces()
        left = [w for w in items if w['name'].lower() != str(name).strip().lower()]
        _save_workspaces(left)
        return len(left) != len(items)


def tree(path, limit=60):
    """Relative file paths of a folder for her prompt (no secrets, no build output, no hidden folders)."""
    out = []
    base = Path(path)
    for dirpath, dirs, names in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d.lower() not in devtools.CODE_SKIP and not devtools.SECRET_RE.search(d.lower()))
        depth = len(Path(dirpath).relative_to(base).parts)
        if depth >= 4:
            dirs[:] = []
        for n in sorted(names):
            if not devtools.SECRET_RE.search(n.lower()) and os.path.splitext(n.lower())[1] in ALLOWED_EXT:
                out.append(str((Path(dirpath) / n).relative_to(base)).replace('\\', '/'))
                if len(out) >= limit:
                    return out
    return out


def workspace_block():
    items = [w for w in workspaces() if os.path.isdir(w['path'])]
    if not items:
        return ''
    lines = []
    for w in items:
        files = tree(w['path'])
        lines.append('- «%s»: %s' % (w['name'], ', '.join(files) if files else 'пока пусто'))
    return '\n'.join(lines)


def _inside(base, target):
    """True when target (resolved, so links and .. cannot trick it) is under base."""
    try:
        return base.resolve() in target.resolve().parents or base.resolve() == target.resolve()
    except OSError:
        return False


def _layout(name, ws):
    """(base = what she may never leave, folder = where the files go)."""
    if ws:
        found = find_workspace(ws)
        if not found:
            raise ValueError('nows')
        base = Path(found['path'])
        return base, base
    base = root()
    return base, base / name


def _plan(name, ws, files):
    """Check the files against the disk. Returns (base, folder, [new directories relative to base]). ValueError('exists'|'path'|'nows')."""
    base, folder = _layout(name, ws)
    dirs = []
    if folder.exists() and not folder.is_dir():
        raise ValueError('path')
    for rel, _ in files:
        target = folder.joinpath(*rel.split('/'))
        if not _inside(base, target) or (target.exists() or target.is_symlink()):
            raise ValueError('exists' if target.exists() else 'path')
        for parent in list(target.parents)[::-1]:
            if _inside(base, parent) and base.resolve() in parent.resolve().parents and not parent.exists() and parent not in dirs:
                dirs.append(parent)
    return base, folder, [str(d.relative_to(base)).replace('\\', '/') for d in dirs]


def propose(src):
    """Validate a project and return the plate {token, file, files, added, removed, diff, cut, folder}.
    ValueError(code): bad | path | secret | ext | big | exists."""
    name, ws, files = parse(src)
    _plan(name, ws, files)
    lines, count = [], 0
    for rel, text in files:
        body = text.split('\n')
        count += len(body)
        lines.append('@@ %s (%d) @@' % (rel, len(body)))
        lines.extend('+' + l for l in body)
    diff = '\n'.join(lines)
    now = time.time()
    with _lock:
        for k in [k for k, v in PENDING.items() if now - v['t'] > TTL]:
            del PENDING[k]
        if len(PENDING) >= MAX_PENDING:
            raise ValueError('bad')
        token = secrets.token_hex(8)
        PENDING[token] = {'t': now, 'name': name, 'ws': ws, 'files': files}
    return {'token': token, 'file': name, 'files': [{'path': r, 'lines': t.count('\n') + 1} for r, t in files], 'added': count,
            'removed': 0, 'inplace': bool(ws), 'diff': diff[:60000], 'cut': len(diff) > 60000}


def apply(token):
    """The creator pressed Apply. Returns {'name','folder','files','manifest','after'} for the journal.
    PermissionError('token'), RuntimeError('rate'|'exists'|'write')."""
    with _lock:
        entry = PENDING.pop(token, None) if isinstance(token, str) else None
        now = time.time()
        if not entry or now - entry['t'] > TTL:
            raise PermissionError('token')
        _stamps[:] = [s for s in _stamps if now - s < 60]
        if len(_stamps) >= 5:
            raise RuntimeError('rate')
        _stamps.append(now)
    try:
        base, folder, dirs = _plan(entry['name'], entry['ws'], entry['files'])   # the disk may have changed since she proposed
    except ValueError:
        raise RuntimeError('exists')
    made, wrote = [], []
    try:
        base.mkdir(parents=True, exist_ok=True)
        for d in dirs:
            (base / d).mkdir(exist_ok=True)
            made.append(d)
        if folder != base and not folder.exists():
            folder.mkdir()
            made.append(entry['name'])
        for rel, text in entry['files']:
            target = folder.joinpath(*rel.split('/'))
            data = text.encode('utf-8')
            with open(target, 'xb') as handle:   # never overwrites
                handle.write(data)
            wrote.append((rel, _sha(data)))
    except OSError:
        _undo_files(folder, wrote, made, base)
        raise RuntimeError('write')
    manifest = {'base': str(base), 'folder': str(folder), 'files': wrote, 'dirs': sorted(set(made), key=len, reverse=True)}
    MANIFESTS.mkdir(exist_ok=True)
    path = MANIFESTS / ('%d_%s.json' % (int(now), secrets.token_hex(3)))
    text = json.dumps(manifest, ensure_ascii=False)
    path.write_text(text, encoding='utf-8')
    return {'name': entry['name'], 'folder': str(folder), 'count': len(wrote), 'manifest': str(path), 'after': _sha(text.encode('utf-8'))}


def _undo_files(folder, wrote, dirs, base):
    for rel, _ in wrote:
        try:
            os.remove(folder.joinpath(*rel.split('/')))
        except OSError:
            pass
    for d in sorted(dirs, key=len, reverse=True):
        try:
            (base / d).rmdir()
        except OSError:
            pass


def restore(manifest_path, after):
    """Take a project back: delete the files she wrote and the folders she made, but only if every file is still exactly what she
    wrote (the creator's own later work is never destroyed). RuntimeError('changed'|'write')."""
    path = Path(manifest_path)
    if MANIFESTS.resolve() not in path.resolve().parents or not path.is_file():
        raise RuntimeError('write')
    try:
        raw = path.read_bytes()
        if _sha(raw) != after:
            raise RuntimeError('write')
        manifest = json.loads(raw.decode('utf-8'))
        folder, base = Path(manifest['folder']), Path(manifest.get('base') or root())
        allowed = [root()] + [Path(w['path']) for w in workspaces()]
        if not any(base.resolve() == a.resolve() for a in allowed) or not _inside(base, folder):
            raise RuntimeError('write')
        present = []
        for rel, sha in manifest['files']:
            target = folder.joinpath(*rel.split('/'))
            if not target.exists():
                continue
            if _sha(target.read_bytes()) != sha:
                raise RuntimeError('changed')
            present.append(rel)
        for rel in present:
            os.remove(folder.joinpath(*rel.split('/')))
        for d in manifest['dirs']:
            try:
                (base / d).rmdir()   # only if empty: anything of his own inside stays
            except OSError:
                pass
        try:
            if folder.resolve() != base.resolve():
                folder.rmdir()   # an empty project folder left behind (an earlier undo kept it) goes too
        except OSError:
            pass
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError('write')
