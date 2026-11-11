"""Her hands, part 2: look for things on this computer and in Google, and open them only after the creator confirms.
The model never sees the file list: it only says what to look for, this module searches locally, and the page asks the
creator "is this it?". Only harmless kinds of things are ever found (shortcuts, documents, media, folders, Steam games):
no scripts and no loose programs from Downloads."""
import os
import re
import secrets
import time
import webbrowser

import devtools
from urllib.parse import quote_plus

# [open:id] (a listed action), [find:name] (look on this computer), [search:words] (Google)
ACT_RE = re.compile(r'\[(open|find|search|do|ue|gd|unity|scan|diff|env|sql|calc|read|run|go|web|doc|move|clip|plan|note):([^\[\]\n]{1,600})\]', re.I)   # [do:task] works the mouse and keyboard (control.py), [ue:op] works Unreal (unreal_bridge.py), [read:file] shows her a code file (devtools.py)

SAFE_EXT = {'.lnk', '.url', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.md',
            '.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp3', '.wav', '.flac', '.mp4', '.mkv', '.avi', '.mov',
            '.psd', '.blend', '.fbx', '.sln', '.unitypackage'}
SKIP_DIRS = {'node_modules', '.git', '__pycache__', 'venv', '.venv', 'appdata', '$recycle.bin', 'cache', '.cache'}
MAX_ITEMS, MAX_SECONDS, TTL, INDEX_TTL = 80000, 5.0, 120, 600

FOUND = {}                     # token -> what the creator may confirm (single use)
_index = {'t': 0.0, 'items': []}


def _env(name):
    return os.environ.get(name) or ''


def _roots():
    home = _env('USERPROFILE') or os.path.expanduser('~')
    start = [os.path.join(_env('ProgramData'), 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
             os.path.join(_env('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs')]
    desk = [os.path.join(home, 'Desktop'), os.path.join(_env('PUBLIC'), 'Desktop'),
            os.path.join(_env('OneDrive'), 'Desktop') if _env('OneDrive') else '']
    user = [os.path.join(home, d) for d in ('Documents', 'Downloads', 'Videos', 'Music', 'Pictures')]
    return [(p, 0, 4) for p in start] + [(p, 1, 3) for p in desk] + [(p, 2, 4) for p in user]


def _steam_games():
    games = []
    base = [os.path.join(_env('ProgramFiles(x86)') or r'C:\Program Files (x86)', 'Steam'),
            os.path.join(_env('ProgramFiles') or r'C:\Program Files', 'Steam')]
    libs = set()
    for b in base:
        if os.path.isdir(b):
            libs.add(os.path.join(b, 'steamapps'))
            try:
                text = open(os.path.join(b, 'steamapps', 'libraryfolders.vdf'), encoding='utf-8', errors='ignore').read()
                libs.update(os.path.join(p.replace('\\\\', '\\'), 'steamapps') for p in re.findall(r'"path"\s+"([^"]+)"', text))
            except OSError:
                pass
    for lib in libs:
        try:
            names = os.listdir(lib)
        except OSError:
            continue
        for n in names:
            if n.startswith('appmanifest_') and n.endswith('.acf'):
                try:
                    t = open(os.path.join(lib, n), encoding='utf-8', errors='ignore').read()
                    appid = re.search(r'"appid"\s+"(\d+)"', t).group(1)
                    name = re.search(r'"name"\s+"([^"]+)"', t).group(1)
                except (OSError, AttributeError):
                    continue
                if 'redistributable' in name.lower() or name.lower().startswith('steamworks'):
                    continue
                games.append({'label': name, 'kind': 'url', 'target': 'steam://rungameid/' + appid, 'where': 'Steam', 'rank': 0})
    return games


def build_index():
    """Names of things worth opening: Start menu / desktop shortcuts, Steam games, documents, media, folders."""
    items, started = _steam_games() + devtools.project_items(), time.time()
    for root, rank, depth in _roots():
        if not root or not os.path.isdir(root):
            continue
        stack = [(root, 0)]
        while stack and len(items) < MAX_ITEMS and time.time() - started < MAX_SECONDS:
            path, d = stack.pop()
            try:
                entries = list(os.scandir(path))
            except OSError:
                continue
            for e in entries:
                low = e.name.lower()
                try:
                    if e.is_dir(follow_symlinks=False):
                        if low in SKIP_DIRS or low.startswith('.'):
                            continue
                        if rank == 2:   # folders of your own: findable too ("открой папку с проектами")
                            items.append({'label': e.name, 'kind': 'dir', 'target': e.path, 'where': e.path, 'rank': rank + 1})
                        if d + 1 < depth:
                            stack.append((e.path, d + 1))
                    elif os.path.splitext(low)[1] in SAFE_EXT and not (rank == 2 and low.endswith(('.lnk', '.url'))):
                        stem = os.path.splitext(e.name)[0]
                        items.append({'label': stem, 'kind': 'file', 'target': e.path, 'where': e.path, 'rank': rank})
                except OSError:
                    continue
    return items


def index():
    if time.time() - _index['t'] > INDEX_TTL:
        _index['items'], _index['t'] = build_index(), time.time()
    return _index['items']


def _tokens(s):
    return re.findall(r'\w+', s.lower())


def find(query, limit=3):
    """Up to `limit` candidates for what the creator asked for, best first; each gets a one-time confirm token."""
    words = _tokens(query)
    if not words:
        return []
    out = _search(words, limit)
    if not out and time.time() - _index['t'] > 30:   # maybe the file is new: look again once
        _index['t'] = 0.0
        out = _search(words, limit)
    return out


def _search(words, limit):
    scored = []
    for it in index():
        name = it['label'].lower()
        if not all(w in name for w in words):
            continue
        score = 50 - min(len(name), 40) * 0.5
        if name == ' '.join(words):
            score += 60
        elif name.startswith(words[0]):
            score += 20
        scored.append((-score, it['rank'], it))
    scored.sort(key=lambda x: (x[0], x[1]))
    out, seen = [], set()
    for _, _, it in scored:
        key = it['label'].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(offer(it['kind'], it['target'], it['label'], it['where']))
        if len(out) >= limit:
            break
    return out


def offer(kind, target, label, where=''):
    now = time.time()
    for k in [k for k, v in FOUND.items() if now - v['t'] > TTL]:
        del FOUND[k]
    token = secrets.token_hex(8)
    FOUND[token] = {'kind': kind, 'target': target, 'label': label, 't': now}
    return {'token': token, 'label': label, 'where': where}


def google(query):
    q = ' '.join(query.split())[:80]
    return offer('url', 'https://www.google.com/search?q=' + quote_plus(q), 'Google: ' + q)


def take(token):
    entry = FOUND.pop(token, None) if isinstance(token, str) else None
    return entry if entry and time.time() - entry['t'] <= TTL else None


def launch(entry):
    kind, target = entry['kind'], entry['target']
    if kind == 'url':
        if target.startswith(('http://', 'https://')):
            webbrowser.open(target)
        elif target.startswith('steam://rungameid/'):
            os.startfile(target)
        else:
            raise OSError('url')
    elif kind == 'dir':
        if not os.path.isdir(target):
            raise OSError('gone')
        os.startfile(target)
    elif kind == 'proj':
        devtools.launch_project(target)
    elif kind == 'file':
        if os.path.splitext(target.lower())[1] not in SAFE_EXT or not os.path.isfile(target):
            raise OSError('gone')
        os.startfile(target)
    else:
        raise OSError('kind')


# What he asked in plain words, when the model forgot to put the command in its reply (a weak model often says "сейчас открою" and stops).
_VERB = r'(?:открой|открыть|открой-ка|запусти|включи|покажи|сделай|найди|поищи)'
_SEARCH_RES = (
    re.compile(r'\b(?:загугли|погугли)\s+(?:мне\s+)?(.+)$', re.I),
    re.compile(_VERB + r'\s+(?:мне\s+)?(?:вкладку\s+)?(?:с\s+)?поиск(?:ом|а)?\s+(?:по\s+)?(?:слов[ауе]|запрос[ауе]?|фраз[еу])?\s*(.+?)(?:\s+(?:в\s+браузере|в\s+гугле|в\s+google|в\s+интернете))?\s*$', re.I),
    re.compile(r'\b(?:поищи|найди)\s+(?:мне\s+)?(?:это\s+)?в\s+(?:гугле|google|браузере)\s+(.+)$', re.I),
    re.compile(r'\b(?:поищи|найди)\s+(.+?)\s+в\s+(?:гугле|google|браузере)\s*$', re.I),
)
_SITE_MARK = re.compile(r'(?i)(?:^|\s)(?:сайт|сайта|site|website|사이트|웹사이트|サイト|ホームページ)(?:\s|$)|(?:사이트|サイト)$')
# "open <name>" in the languages he talks in: Russian and English put the verb first, Korean and Japanese put it last
_OPEN_PRE = re.compile(r'(?i)^(?:пожалуйста,?\s*|please,?\s*|plz\s+|луна,?\s*|luna,?\s*)?'
                       r'(?:открой(?:те)?(?:-ка)?|открыть|запусти(?:ть)?|зайди\s+на|перейди\s+на|включи|покажи|'
                       r'open|launch|go\s+to|visit|take\s+me\s+to|pull\s+up|show\s+me)\s+(?:мне\s+|me\s+|up\s+)?(.+?)\s*[.!?]*$')
_OPEN_KO = re.compile(r'^(?:루나[,\s]*)?(.+?)\s*(?:을|를)?\s*(?:열어\s*줘요?|열어\s*주세요|열어\s*봐|열어|켜\s*줘요?|켜\s*주세요|가\s*줘|들어가\s*줘|띄워\s*줘|보여\s*줘|보여\s*주세요)\s*[.!?]*$')
_OPEN_JA = re.compile(r'^(?:ルナ[、,\s]*)?(.+?)\s*(?:を|に)?\s*(?:開いて|開けて|開く|見せて|立ち上げて|起動して|行って)(?:ください|くれ)?\s*[。.!?]*$')
_SEARCH_MORE = (
    re.compile(r'(?i)^(?:please\s+)?(?:google|search\s+for|search\s+google\s+for|search(?:\s+the\s+(?:web|internet|net))?(?:\s+for)?|look\s+up|find\s+(?:me\s+)?(?:on\s+the\s+(?:web|internet)\s+)?)\s+(.+?)\s*[.!?]*$'),
    re.compile(r'(?i)^(?:луна,?\s*)?(?:поищи|найди|погугли|поищите|найдите)\s+(?:мне\s+)?(?:в\s+(?:интернете|интернет|сети|инете))\s+(.+?)\s*[.!?]*$'),
    re.compile(r'(?i)^(?:луна,?\s*)?(?:поищи|найди|поищите|найдите)\s+(.+?)\s+(?:в\s+(?:интернете|интернет|сети|инете))\s*[.!?]*$'),
    re.compile(r'^(.+?)\s*(?:을|를)?\s*(?:검색해\s*줘요?|검색해\s*주세요|검색해\s*봐|구글링해\s*줘|찾아\s*줘|찾아\s*봐|알아\s*봐\s*줘|알아봐\s*줘)\s*[.!?]*$'),
    re.compile(r'^(.+?)\s*(?:を)?\s*(?:検索して|ググって|検索してください|調べて|調べてください|探して|探してください)\s*[。.!?]*$'),
)
_LOCAL_THING = re.compile(r'(?i)(файл|папк|документ|\bfile|\bfolder|파일|폴더|문서|ファイル|フォルダ|ドキュメント|書類)')
_WEB_PREFIX = re.compile(r'^(?:(?:인터넷|웹|구글|네이버)(?:에서|으로)?\s*|(?:ネット|インターネット|ウェブ|グーグル|Google)(?:で|を)\s*)', re.I)


def intent_commands(text, known):
    """[('search', words) | ('go', site)] read straight from his sentence (in any of his languages).
    known(name) says whether a name is a site we can open at once (a listed name or a public address). A name that is not
    known becomes a go-command only when he said it is a site (сайт / site / 사이트 / サイト): then it is searched and he confirms."""
    text = ' '.join(str(text or '').split())[:300]
    for rx in _SEARCH_RES + _SEARCH_MORE:
        m = rx.search(text)
        q = re.split(r'[,;]', m.group(1))[0] if m else ''
        q = re.sub(r'\s+(?:в\s+браузере|в\s+гугле|в\s+google|в\s+интернете)$', '', q.strip(' .!?"«»'), flags=re.I).strip()
        q = _WEB_PREFIX.sub('', q).strip()
        if q and not _LOCAL_THING.search(q):   # a file or a folder is looked for on this computer, not on the web
            return [('search', q.lower()[:80])]
    for rx in (_OPEN_PRE, _OPEN_KO, _OPEN_JA):
        m = rx.match(text)
        if not m:
            continue
        name = m.group(1).strip()
        if not 1 <= len(name) <= 80:
            continue
        if known(name):
            return [('go', name)]
        if _SITE_MARK.search(name) or _SITE_MARK.search(text):
            return [('go', name)]
    return []
