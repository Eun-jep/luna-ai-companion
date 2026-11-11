"""The song library: audio files the creator adds, which she can perform on request ("спой <название>").

Files live in songs/ under names the program makes up (never a name that came from outside), the list in songs/library.json.
Only audio is accepted (checked by the file's first bytes, not by its name), at most MAX_BYTES each and MAX_SONGS in all.
Tempo and length come from the page, which decodes the audio. Pure standard library."""
import paths
import json
import re
import secrets
import time
from pathlib import Path

DIR = paths.data_file('songs')
INDEX = DIR / 'library.json'
MAX_BYTES = 80 << 20
MAX_SONGS = 60
EXT = {'mp3': '.mp3', 'wav': '.wav', 'ogg': '.ogg', 'flac': '.flac', 'm4a': '.m4a'}
ID = re.compile(r'^[0-9a-f]{12}$')


def kind(head):
    """Audio format by the first bytes ('' when it is not audio we accept)."""
    if head[:3] == b'ID3' or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return 'mp3'
    if head[:4] == b'RIFF' and head[8:12] == b'WAVE':
        return 'wav'
    if head[:4] == b'OggS':
        return 'ogg'
    if head[:4] == b'fLaC':
        return 'flac'
    if head[4:8] == b'ftyp':
        return 'm4a'
    return ''


def load():
    try:
        data = json.loads(INDEX.read_text(encoding='utf-8'))
        return [s for s in data if isinstance(s, dict) and ID.match(str(s.get('id', ''))) and s.get('ext') in EXT.values()]   # 'her' is a plain flag read with s.get
    except (OSError, ValueError, TypeError):
        return []


def _save(songs):
    DIR.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(songs, ensure_ascii=False, indent=1), encoding='utf-8')


def clean_title(name):
    """A file name -> a readable title: no extension, no folders, no odd characters, no longer than 80."""
    name = re.sub(r'\.[A-Za-z0-9]{2,5}$', '', str(name or '').replace('\\', '/').split('/')[-1])
    name = re.sub(r'[\x00-\x1f<>"|?*]', ' ', name).replace('_', ' ')
    return ' '.join(name.split())[:80] or 'Песня'


def add(name, data, her=False):
    """Store the audio -> the new entry; ValueError('format'|'size'|'full') when it cannot be taken. her=True: a cover sung in her own voice."""
    if not isinstance(data, (bytes, bytearray)) or not 1024 <= len(data) <= MAX_BYTES:
        raise ValueError('size')
    fmt = kind(bytes(data[:16]))
    if not fmt:
        raise ValueError('format')
    songs = load()
    if len(songs) >= MAX_SONGS:
        raise ValueError('full')
    sid = secrets.token_hex(6)
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / (sid + EXT[fmt])).write_bytes(bytes(data))
    entry = {'id': sid, 'title': clean_title(name), 'ext': EXT[fmt], 'bpm': 0, 'secs': 0, 'added': int(time.time())}
    if her:
        entry['her'] = True
    songs.append(entry)
    _save(songs)
    return entry


def get(sid):
    return next((s for s in load() if s['id'] == sid), None)


def path(sid):
    s = get(sid) if isinstance(sid, str) and ID.match(sid) else None
    p = DIR / (s['id'] + s['ext']) if s else None
    return p if p and p.is_file() else None


def set_info(sid, bpm, secs):
    songs = load()
    for s in songs:
        if s['id'] == sid:
            if isinstance(bpm, (int, float)) and not isinstance(bpm, bool) and 40 <= bpm <= 220:
                s['bpm'] = int(round(bpm))
            if isinstance(secs, (int, float)) and not isinstance(secs, bool) and 1 <= secs <= 3600 * 2:
                s['secs'] = int(round(secs))
            _save(songs)
            return s
    return None


def rename(sid, title):
    songs = load()
    for s in songs:
        if s['id'] == sid:
            s['title'] = clean_title(title)
            _save(songs)
            return s
    return None


def remove(sid):
    if not isinstance(sid, str) or not ID.match(sid):
        return False
    songs = load()
    keep = [s for s in songs if s['id'] != sid]
    if len(keep) == len(songs):
        return False
    for s in songs:
        if s['id'] == sid:
            try:
                (DIR / (s['id'] + s['ext'])).unlink()
            except OSError:
                pass
    _save(keep)
    return True


def words(text):
    return [w for w in re.sub(r'[^\w]+', ' ', str(text).lower().replace('ё', 'е')).split() if len(w) > 1 or w.isdigit()]


FILLER = {'спой', 'спеть', 'спойте', 'попой', 'напой', 'пожалуйста', 'песню', 'песни', 'песня', 'мне', 'ты', 'луна', 'луну', 'давай',
          'можешь', 'хочу', 'чтобы', 'ну', 'так', 'ещё', 'еще', 'эту', 'свою', 'нам', 'для', 'меня', 'sing', 'please', 'song', 'the', 'a'}


def find(query):
    """The song the creator named, or None. Every meaningful word of the request has to be in the title: 'спой про дождь' names
    nothing in the library (so she makes up her own), 'спой Дождь' names a song called 'Дождь'."""
    asked = [w for w in words(query) if w not in FILLER]
    if not asked:
        return None
    best, score = None, 0.0
    for s in load():
        title = set(words(s['title']))
        if not title:
            continue
        hit = sum(1 for w in asked if w in title or any(len(w) >= 4 and (t.startswith(w[:5]) or w.startswith(t[:5])) for t in title if len(t) >= 4))
        if hit == len(asked):
            sc = hit / len(title) + 0.5
            if sc > score:
                best, score = s, sc
    return best


def titles(limit=20):
    return [s['title'] for s in load()][:limit]
