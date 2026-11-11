"""Her hands, part 3: the creator's own documents. Find a file or a folder by name (or by what is written inside), read it (PDF, Word,
Excel, PowerPoint, text), look into a folder, and tidy up by moving a file. Reading and moving always wait for the creator's press;
a move goes to the journal and can be taken back. Only the usual personal folders (Documents, Desktop, Downloads, Pictures, Music,
Videos) are searched; keys, passwords and system folders are never offered. Pure standard library plus the Office/PDF readers."""
import os
import re
import secrets
import shutil
import time
from pathlib import Path

from luna.skills import tables

TTL = 120
MAX_SEND = 9000                  # characters of a document she reads at once
MAX_FILE = 25 << 20
MAX_DIGEST = 6000                # characters of the exact table summary that follow the text
TEXT_EXT = {'.txt', '.md', '.csv', '.json', '.log', '.ini', '.xml', '.yaml', '.yml', '.html', '.htm', '.rtf', '.tsv'}
DOC_EXT = TEXT_EXT | {'.pdf', '.docx', '.xlsx', '.pptx'}
SECRET_RE = re.compile(r'(^\.env|secret|credential|password|passwd|пароль|token|apikey|api_key|private|id_rsa|\.pem$|\.key$|\.pfx$|wallet|seed)', re.I)
SKIP_DIRS = {'node_modules', '.git', '__pycache__', 'venv', '.venv', 'appdata', '$recycle.bin', 'cache', '.cache', 'windows'}
MAX_SCAN, SCAN_SECONDS = 30000, 5.0
PENDING = {}                     # token -> {'kind', 'path', ...}: what the creator may confirm (single use)
ROOTS = None                     # tests point this at a temporary folder
ALIASES = {'документы': 'Documents', 'documents': 'Documents', 'загрузки': 'Downloads', 'downloads': 'Downloads', 'рабочий стол': 'Desktop', 'desktop': 'Desktop',
           'картинки': 'Pictures', 'изображения': 'Pictures', 'pictures': 'Pictures', 'музыка': 'Music', 'music': 'Music', 'видео': 'Videos', 'videos': 'Videos'}


def roots():
    if ROOTS is not None:
        return [Path(r) for r in ROOTS]
    home = Path(os.environ.get('USERPROFILE') or os.path.expanduser('~'))
    out = [home / d for d in ('Documents', 'Desktop', 'Downloads', 'Pictures', 'Music', 'Videos')]
    one = os.environ.get('OneDrive')
    if one:
        out += [Path(one) / d for d in ('Documents', 'Desktop')]
    return [r for r in out if r.is_dir()]


def inside(path):
    """Is this path under one of the allowed roots (symlinks resolved)?"""
    try:
        p = Path(path).resolve()
    except OSError:
        return False
    return any(r.resolve() == p or r.resolve() in p.parents for r in roots())


def _words(query):
    return re.findall(r'[\w.]+', str(query or '').lower())


def _walk(limit_depth=5):
    """Files and folders of the allowed roots: (path, is_dir). Bounded in count and time."""
    started, n = time.time(), 0
    for root in roots():
        stack = [(root, 0)]
        while stack:
            d, depth = stack.pop()
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            for e in entries:
                n += 1
                if n > MAX_SCAN or time.time() - started > SCAN_SECONDS:
                    return
                try:
                    isdir = e.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                low = e.name.lower()
                if SECRET_RE.search(low) or low in SKIP_DIRS or low.startswith('.'):
                    continue
                if isdir:
                    yield Path(e.path), True
                    if depth < limit_depth:
                        stack.append((Path(e.path), depth + 1))
                elif os.path.splitext(low)[1] in DOC_EXT or os.path.splitext(low)[1] in {'.jpg', '.jpeg', '.png', '.gif', '.zip', '.mp3', '.mp4', '.exe', '.msi', '.7z', '.rar'}:
                    yield Path(e.path), False


def _offer(kind, path, extra=None):
    now = time.time()
    for k in [k for k, v in PENDING.items() if now - v['t'] > TTL]:
        del PENDING[k]
    token = secrets.token_hex(8)
    PENDING[token] = dict(extra or {}, kind=kind, path=str(path), t=now)
    return {'token': token, 'label': Path(path).name, 'where': str(Path(path).parent), 'dir': kind == 'dir'}


def find(query, limit=3):
    """Documents and folders whose name has every word of the request, best first. Else files that contain the words inside (limit 3)."""
    words = _words(query)
    if not words:
        return []
    alias = ALIASES.get(' '.join(words))
    if alias:
        for r in roots():
            if r.name == alias:
                return [_offer('dir', r)]
    scored = []
    for p, isdir in _walk():
        name = p.name.lower()
        if all(w in name for w in words) and (isdir or p.suffix.lower() in DOC_EXT):
            score = 50 - min(len(name), 40) * 0.5 + (60 if name == ' '.join(words) else 20 if name.startswith(words[0]) else 0) + (10 if isdir else 0)
            scored.append((-score, p, isdir))
    scored.sort(key=lambda x: x[0])
    out = [_offer('dir' if d else 'file', p) for _, p, d in scored[:limit]]
    return out or grep(words, limit)


def grep(words, limit=3):
    """Text-like documents (txt, md, csv, docx, pdf up to a size) that contain every word in their text. Slow path: bounded."""
    words = [w for w in words if len(w) >= 3] or words
    hits = []
    for p, isdir in _walk(3):
        if isdir or p.suffix.lower() not in (TEXT_EXT | {'.docx', '.pdf'}):
            continue
        try:
            if p.stat().st_size > 3 << 20:
                continue
            low = _extract(p, 20000).lower()
        except (OSError, ValueError, RuntimeError):
            continue
        if all(w in low for w in words):
            hits.append(p)
            if len(hits) >= limit:
                break
    return [_offer('file', p) for p in hits]


def _extract(path, limit):
    """Text of a document. OSError / ValueError / RuntimeError('need:pypdf') when it cannot be read."""
    path = Path(path)
    ext = path.suffix.lower()
    if path.stat().st_size > MAX_FILE:
        raise ValueError('big')
    if ext in TEXT_EXT:
        raw = path.read_bytes()[:limit * 4 + 4]
        for enc in ('utf-8-sig', 'cp1251'):
            try:
                return raw.decode(enc)[:limit]
            except UnicodeDecodeError:
                continue
        return raw.decode('utf-8', errors='replace')[:limit]
    if ext == '.docx':
        try:
            import docx
        except ImportError:
            raise RuntimeError('need:python-docx')
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for t in d.tables[:5]:
            for row in t.rows[:40]:
                parts.append(' | '.join(c.text.strip() for c in row.cells))
        return '\n'.join(parts)[:limit]
    if ext == '.xlsx':
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError('need:openpyxl')
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        parts = []
        for ws in wb.worksheets[:4]:
            parts.append('# ' + ws.title)
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= 80:
                    parts.append('...')
                    break
                parts.append(' | '.join('' if c is None else str(c) for c in row[:20]))
        wb.close()
        return '\n'.join(parts)[:limit]
    if ext == '.pptx':
        try:
            import pptx
        except ImportError:
            raise RuntimeError('need:python-pptx')
        parts = []
        for n, slide in enumerate(pptx.Presentation(str(path)).slides, 1):
            parts.append('# слайд %d' % n)
            for shape in slide.shapes:
                if shape.has_text_frame and shape.text_frame.text.strip():
                    parts.append(shape.text_frame.text.strip())
        return '\n'.join(parts)[:limit]
    if ext == '.pdf':
        try:
            import pypdf
        except ImportError:
            raise RuntimeError('need:pypdf')
        parts, size = [], 0
        try:
            reader = pypdf.PdfReader(str(path))
            if reader.is_encrypted:
                raise ValueError('locked')
            for page in reader.pages[:60]:
                t = page.extract_text() or ''
                parts.append(t)
                size += len(t)
                if size > limit:
                    break
        except ValueError:
            raise
        except Exception:   # pypdf has its own family of errors for damaged files
            raise ValueError('broken')
        return '\n'.join(parts)[:limit]
    raise ValueError('type')


def read(token):
    """What the creator agreed to show her -> {'name','text','truncated','dir'}. PermissionError (bad token), OSError / ValueError / RuntimeError."""
    entry = PENDING.pop(token, None) if isinstance(token, str) else None
    if not entry or entry['kind'] not in ('file', 'dir') or time.time() - entry['t'] > TTL:
        raise PermissionError('token')
    path = Path(entry['path'])
    if not inside(path) or SECRET_RE.search(path.name):
        raise OSError('place')
    if entry['kind'] == 'dir':
        rows = []
        for e in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower())):
            if SECRET_RE.search(e.name) or e.name.startswith('.'):
                continue
            try:
                rows.append(('[папка] ' if e.is_dir() else '') + e.name + ('' if e.is_dir() else ' (%s)' % _size(e.stat().st_size)))
            except OSError:
                continue
        text = '\n'.join(rows[:200])
        return {'name': path.name, 'text': text or '(пусто)', 'truncated': len(rows) > 200, 'dir': True}
    if not path.is_file():
        raise OSError('missing')
    text = _extract(path, MAX_SEND + 1)
    shown = text[:MAX_SEND] or '(в документе нет текста)'
    try:   # a table also gets exact numbers computed over the whole file
        summary = tables.digest(path)[:MAX_DIGEST]
    except (OSError, ValueError, RuntimeError):
        summary = ''
    if summary:
        shown += '\n\n' + summary
    return {'name': path.name, 'text': shown, 'truncated': len(text) > MAX_SEND, 'dir': False}


def _size(n):
    for unit in ('Б', 'КБ', 'МБ', 'ГБ'):
        if n < 1024 or unit == 'ГБ':
            return '%d %s' % (n, unit) if unit == 'Б' else '%.1f %s' % (n, unit)
        n /= 1024


# ---- tidying up: one file into one folder, with a way back ----
def propose_move(spec):
    """'file name >> folder name' -> a plate {'token','label','to','where'} or {'fail': code}. Both stay inside the allowed folders; nothing is overwritten."""
    if '>>' not in str(spec):
        return {'fail': 'form'}
    name, _, folder = (s.strip().strip('"') for s in str(spec).partition('>>'))
    if not name or not folder or re.search(r'[\\/:*?"<>|]', folder) or folder in ('.', '..') or SECRET_RE.search(name):
        return {'fail': 'form'}
    src = [p for p, isdir in _walk() if not isdir and p.name.lower() == name.lower()]
    if not src:
        return {'fail': 'nofile'}
    if len(src) > 1:
        return {'fail': 'many'}
    src = src[0]
    alias = ALIASES.get(folder.lower())
    dest = next((r for r in roots() if alias and r.name == alias), None)
    if dest is None:
        match = [p for p, isdir in _walk() if isdir and p.name.lower() == folder.lower()]
        dest = match[0] if match else src.parent / folder   # a new folder next to the file
    if not inside(dest) or dest.resolve() == src.parent.resolve():
        return {'fail': 'same' if dest.exists() else 'place'}
    if (dest / src.name).exists():
        return {'fail': 'exists'}
    plate = _offer('move', src, {'dest': str(dest)})
    return {'token': plate['token'], 'label': src.name, 'to': str(dest), 'where': str(src.parent)}


def move(token):
    """The creator pressed Move: do exactly that -> {'name','old','new'}. PermissionError / OSError."""
    entry = PENDING.pop(token, None) if isinstance(token, str) else None
    if not entry or entry['kind'] != 'move' or time.time() - entry['t'] > TTL:
        raise PermissionError('token')
    src, dest = Path(entry['path']), Path(entry['dest'])
    if not src.is_file() or not inside(src) or not inside(dest) or (dest / src.name).exists():
        raise OSError('state')
    dest.mkdir(parents=True, exist_ok=True)
    new = dest / src.name
    shutil.move(str(src), str(new))
    return {'name': src.name, 'old': str(src), 'new': str(new)}


def restore(old, new):
    """Undo a move: the file goes back where it was, if it is still where we put it and the old place is free."""
    old, new = Path(old), Path(new)
    if not inside(old) or not inside(new):
        raise RuntimeError('cannot')
    if not new.is_file():
        raise RuntimeError('gone')
    if old.exists():
        raise RuntimeError('exists')
    old.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(new), str(old))
    if new.parent.resolve() not in [r.resolve() for r in roots()]:
        try:
            new.parent.rmdir()   # the folder made for the move goes too, if nothing else is in it
        except OSError:
            pass
