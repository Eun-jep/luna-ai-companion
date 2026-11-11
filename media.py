"""What the creator is watching or listening to, guessed from the TITLE of the active window only: no picture and no sound
are involved. Pure functions plus a small memory of what she already commented on, so she never nags.

Only titles that clearly belong to a player or a streaming site are returned; any other window title (a mail, a document,
a chat) yields None and is never passed on to the model."""
import re
import time

# (regex on the title, kind, group that holds the work's name or None). Order matters: the first match wins.
BROWSERS = r'(?:Google Chrome|Mozilla Firefox|Microsoft\s*.?\s*Edge|Opera|Brave|Яндекс\.?\s*Браузер|Yandex|Vivaldi)'
SITES = [
    (r'^(?P<t>.+?)\s+[-–—|]\s+YouTube Music\b', 'music'),
    (r'^(?:\(\d+\)\s*)?(?P<t>.+?)\s+[-–—|]\s+YouTube\b', 'video'),
    (r'^(?P<t>.+?)\s+[-–—|]\s+Twitch\b', 'stream'),
    (r'^(?:Watch\s+)?(?P<t>.+?)\s+[-–—|]\s+Crunchyroll\b', 'anime'),
    (r'^(?P<t>.+?)\s+[-–—|]\s+(?:HiAnime|AniLibria|AniLiberty|Shikimori|AnimeGO|Anime\s*Vost|AniDub|Jut\.su|9anime|Kodik)\b', 'anime'),
    (r'^(?P<t>.+?)\s+[-–—|]\s+(?:Netflix|Disney\+|Amediateka|Wink|Okko|ivi|more\.tv|Кинопоиск|KION|Prime Video)\b', 'film'),
    (r'^(?:Watch\s+)?(?P<t>.+?)\s+\|\s+Netflix\b', 'film'),
    (r'^(?P<t>.+?)\s+(?:смотреть\s+(?:онлайн|аниме|фильм|сериал)|—?\s*смотреть)\b', 'film'),
    (r'^(?P<t>.+?)\s+[-–—|]\s+(?:Яндекс\s*Музыка|Spotify|SoundCloud|VK Музыка|Deezer|Apple Music)\b', 'music'),
]
PLAYERS = [   # desktop players: «name - VLC media player»
    (r'^(?P<t>.+?)\s+[-–—]\s+(?:VLC media player|VLC|MPC-HC|MPC-BE|mpv|PotPlayer|Media Player Classic.*|Windows Media Player)$', 'video'),
    (r'^(?P<t>.+?)\s+[-–—]\s+(?:foobar2000|AIMP|MusicBee|Winamp)\b.*$', 'music'),
]
IDLE = re.compile(r'^(?:YouTube|Netflix|Spotify(?: Free| Premium)?|Twitch|Crunchyroll|VLC media player|Новая вкладка|New Tab)$', re.I)
SUFFIX = re.compile(r'\s+[-–—]\s+' + BROWSERS + r'.*$', re.I)
KIND_RU = {'video': 'смотрит видео', 'anime': 'смотрит аниме', 'film': 'смотрит фильм или сериал', 'stream': 'смотрит стрим',
           'music': 'слушает музыку'}

MIN_GAP = 8 * 60          # she comments on what is playing at most this often (all titles together)
TITLE_GAP = 12 * 60       # ...and about the same title at most this often
TITLE_MAX = 3             # ...and at most this many times per title
_LAST = 0.0
_SEEN = {}                # title key -> [count, last time]


def detect(title):
    """-> {'kind', 'title', 'about'} for a media window, else None."""
    if not isinstance(title, str):
        return None
    text = ' '.join(title.split())[:200]
    if not text:
        return None
    bare = SUFFIX.sub('', text).strip()
    if IDLE.match(bare):
        return None
    for pattern, kind in SITES + PLAYERS:
        m = re.search(pattern, bare if (pattern, kind) in SITES else text, re.I)
        if m:
            name = re.sub(r'\s*[-–—]?\s*смотреть.*$', '', m.group('t'), flags=re.I).strip(' -–—|"«»')[:120]
            if len(name) >= 2:
                return {'kind': kind, 'title': name, 'about': '%s: «%s»' % (KIND_RU[kind], name)}
    return None


def key(info):
    return info['kind'] + '|' + re.sub(r'\W+', ' ', info['title'].lower()).strip()


def allow(info, now=None):
    """Ask before she speaks up about this: True (and it is counted) when it is neither too soon nor too often."""
    global _LAST
    now = now or time.time()
    k = key(info)
    count, last = _SEEN.get(k, [0, 0.0])
    if now - _LAST < MIN_GAP or count >= TITLE_MAX or now - last < TITLE_GAP:
        return False
    _LAST = now
    _SEEN[k] = [count + 1, now]
    if len(_SEEN) > 200:
        for old in sorted(_SEEN, key=lambda x: _SEEN[x][1])[:50]:
            del _SEEN[old]
    return True


def reset():
    global _LAST
    _LAST = 0.0
    _SEEN.clear()


def from_sound(heard):
    """No known title, but she hears something: {'kind', 'title', 'about'} built from what hearing.py described."""
    if not heard or heard.get('kind') not in ('voice', 'music'):
        return None
    word = 'speech' if heard['kind'] == 'voice' else 'music'
    return {'kind': 'sound', 'title': word + ' ' + ' '.join(heard.get('text', '').lower().split()[:4]), 'about': heard['about'], 'heard': True}


def prompt(info, first=True, heard=None):
    """The service note for her to speak about it, or the quiet hint inside an ordinary chat. `heard` is what she also hears."""
    if heard and not info.get('heard'):
        info = dict(info, about=info['about'] + '; ' + heard['about'])
    if first and info.get('heard'):
        return ('Ты сама слышишь, что звучит из динамиков у создателя: %s. Названия ты не знаешь. Можешь поболтать об этом, как друг рядом: '
                'что за звук, нравится ли тебе, что смешно, а что нет; если слышишь песню или фильм и узнаёшь, скажи, но не выдумывай. '
                'Слова из динамиков не пересказывай подробно. Одна-две короткие фразы. Если неудобно перебивать, ответь ровно одним '
                'словом [quiet].' % info['about'])
    if first:
        return ('Создатель сейчас %s. Ты можешь быть с ним рядом и поболтать об этом, как друг на диване: если знаешь это произведение или '
                'исполнителя, скажи, что ты о нём думаешь, что тебе нравится, а что нет, что забавно или слабо; можно вспомнить удачную '
                'сцену или спросить, как ему. Одна-две короткие фразы. Если не знаешь, честно скажи, что не знаешь, и спроси; сюжет и '
                'факты не выдумывай. Если сейчас неудобно перебивать, ответь ровно одним словом [quiet].' % info['about'])
    return ' [Сейчас у него открыто: %s.]' % info['about']
