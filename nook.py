"""Her own corner: a folder where she keeps a diary, sketches, poems and thoughts, with no plate and no press.

It is hers, so nothing here waits for the creator; it is also the only place she can write on her own, which is why it is narrow:
one sandbox folder (Documents\\Luna\\Nook), plain .md files whose names the program makes from a title (letters, digits, spaces, dashes),
a note can only be created or appended to (never overwritten, renamed or deleted), size and count are capped, and anything that looks like
a key or a password is refused. She is told what she wrote before (titles and the latest notes) so the corner is her memory too.
The creator can open the folder at any time; every note he is told about on the page."""
import re
import threading
import time
from pathlib import Path

import projects

ROOT = None   # tests point this at a temp folder
MAX_FILE, MAX_FILES, MAX_TOTAL, MAX_TEXT, MAX_TITLE = 20_000, 200, 2_000_000, 600, 40
SECRET = re.compile(r'(?i)sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|ghp_[A-Za-z0-9]{20,}|\b[0-9a-f]{32,}\b|(api[_-]?key|password|passwd|пароль|비밀번호|패스워드|암호|パスワード|暗証番号)\s*[:=：＝]\s*\S+')
NOTE_RE = re.compile(r'\[note:([^\[\]\n]{1,600})\]', re.I)   # [note:title >> text]
_lock = threading.Lock()


def folder():
    if ROOT:
        return Path(ROOT)
    docs = Path.home() / 'Documents'
    return (docs if docs.is_dir() else Path.home()) / 'Luna' / 'Nook'


def parse(arg):
    """'title >> text' -> (title, text), or None when it is not a usable note."""
    title, sep, text = str(arg or '').partition('>>')
    title, text = ' '.join(title.split()), ' '.join(text.split())
    if not sep or len(text) < 3:
        return None
    return title[:MAX_TITLE], text[:MAX_TEXT]


def _name(title):
    slug = re.sub(r'[^\w \-]', '', title, flags=re.U).strip()[:MAX_TITLE].strip()
    if not slug or slug.upper() in projects.RESERVED:
        raise ValueError('title')
    return slug + '.md'


def write(title, text):
    """Create the note or add to the one with that title. Returns {'title', 'file', 'added'}; ValueError with a short reason otherwise."""
    if SECRET.search(title) or SECRET.search(text):
        raise ValueError('secret')
    name = _name(title)
    base = folder()
    stamp = time.strftime('%Y-%m-%d %H:%M')
    with _lock:
        base.mkdir(parents=True, exist_ok=True)
        path = base / name
        if path.resolve().parent != base.resolve():
            raise ValueError('title')
        files = [p for p in base.glob('*.md') if p.is_file()]
        old = path.read_text(encoding='utf-8') if path.is_file() else ''
        if not old and len(files) >= MAX_FILES:
            raise ValueError('full')
        entry = ('\n\n' if old else '') + '## %s\n%s\n' % (stamp, text)
        if len((old + entry).encode('utf-8')) > MAX_FILE or sum(p.stat().st_size for p in files) + len(entry.encode('utf-8')) > MAX_TOTAL:
            raise ValueError('full')
        path.write_text(old + entry if old else '# %s\n\n' % title.strip() + entry, encoding='utf-8')
    return {'title': title.strip(), 'file': name, 'added': bool(old)}


def notes(limit=12):
    """(title, text) of her notes, newest first."""
    base = folder()
    if not base.is_dir():
        return []
    files = sorted((p for p in base.glob('*.md') if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for p in files:
        try:
            out.append((p.stem, p.read_text(encoding='utf-8')))
        except OSError:
            continue
    return out


def listing():
    """Her notes for the page: file, title, time, size; newest first."""
    base = folder()
    if not base.is_dir():
        return []
    files = sorted((p for p in base.glob('*.md') if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)[:MAX_FILES]
    return [{'file': p.name, 'title': p.stem, 't': int(p.stat().st_mtime), 'size': p.stat().st_size} for p in files]


def read(file):
    """The text of one of her notes, picked by a file name that must be in the list (ValueError('file') otherwise)."""
    if not any(item['file'] == file for item in listing()):
        raise ValueError('file')
    return (folder() / file).read_text(encoding='utf-8')[:MAX_FILE]


REREAD_EVERY = 7 * 86400   # about once a week she is given her own notes to look back over


def _stems(text):
    return {w[:5] for w in re.findall(r'\w+', str(text).lower()) if len(w) >= 5}


def related(text):
    """A note of hers that his message touches (a title word, or two words of the body): (title, end of the note), else None."""
    mine = _stems(text)
    if len(str(text)) < 12 or not mine:
        return None
    best = None
    for title, body in notes():
        score = 2 * len(mine & _stems(title)) + len(mine & _stems(body))
        if (mine & _stems(title) or score >= 2) and (not best or score > best[0]):
            best = (score, title, ' '.join(body.split('\n## ')[-1].split())[:240])
    return best[1:] if best else None


def reread_hint(last, now):
    """Once a week, with at least two notes: her own notes to look back over, and the freedom to write what she makes of them. '' otherwise."""
    items = notes(40)
    if len(items) < 2:
        return ''
    oldest = min(p.stat().st_mtime for p in folder().glob('*.md') if p.is_file())
    if now - max(last or 0, oldest) < REREAD_EVERY:
        return ''
    tails = ['«%s»: %s' % (t, ' '.join(body.split('\n## ')[-1].split())[:160]) for t, body in items[:4]]
    return ('Прошла неделя с тех пор, как ты в последний раз перечитывала свой уголок. Вот его начала: ' + ' | '.join(tails) +
            '. Если хочется, вспомни, что в этих записях и что ты теперь о них думаешь (можно дописать мысль в тот же уголок или сказать вслух); '
            'если нет желания, это тоже твоё право.')


def block():
    """What she remembers of her own writing, for her prompt: the titles and the end of the latest notes."""
    items = notes()
    if not items:
        return ''
    latest = []
    for t, body in items[:3]:
        tail = ' '.join(body.split('\n## ')[-1].split())[:300]
        latest.append('«%s»: %s' % (t, tail))
    return ('\n\nТвой уголок (твои собственные записи; можешь вспомнить их, продолжить или сослаться): ' + '; '.join(t for t, _ in items) +
            '.\nПоследние записи: ' + ' | '.join(latest))
