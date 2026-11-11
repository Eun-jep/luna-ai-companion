"""Noticing what is watched or listened to from the window title (media.py + the /chat endpoint)."""
import os
import sys, tempfile, pathlib, threading, json, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import media
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

D = media.detect
ok('standalone module', 'app' not in sys.modules)
cases = [
    ('Rick Astley - Never Gonna Give You Up - YouTube - Google Chrome', 'video', 'Rick Astley - Never Gonna Give You Up'),
    ('(3) Видео про котов - YouTube — Mozilla Firefox', 'video', 'Видео про котов'),
    ('Watch Frieren Episode 5 - Crunchyroll - Google Chrome', 'anime', 'Frieren Episode 5'),
    ('Frieren - AniLibria - Opera', 'anime', 'Frieren'),
    ('Stranger Things | Netflix - Google Chrome', 'film', 'Stranger Things'),
    ('Гравити Фолз смотреть онлайн - Кинопоиск', 'film', 'Гравити Фолз'),
    ('movie.mkv - VLC media player', 'video', 'movie.mkv'),
    ('Kino - Группа крови - YouTube Music', 'music', 'Kino - Группа крови'),
    ('Артист — Трек — Яндекс Музыка', 'music', 'Артист — Трек'),
    ('xQc - Twitch', 'stream', 'xQc')]
for title, kind, name in cases:
    d = D(title)
    ok('«%s» -> %s / %s' % (title, kind, name), d is not None and d['kind'] == kind and d['title'] == name)
for title in ['Re: Счёт за март - Gmail - Google Chrome', 'YouTube - Google Chrome', 'Новая вкладка - Google Chrome', 'Document1 - Word', 'Blender',
              'Пароль для банка - Notepad', 'Spotify Free', '', '   ', None, 42, 'x' * 5000]:
    ok('not media, never passed on: %r' % (title if not isinstance(title, str) else title[:30]), D(title) is None)
ok('long titles are cut', len(D('a' * 150 + ' - YouTube')['title']) <= 120)
ok('a huge title is not passed on at all', D('a' * 1000 + ' - YouTube') is None)

# not nagging
media.reset()
info = D('Frieren - AniLibria - Opera'); other = D('Stranger Things | Netflix - Google Chrome')
ok('first time she may speak', media.allow(info, 1000))
ok('not again right away, about anything', not media.allow(info, 1100) and not media.allow(other, 1100))
ok('after the global gap another title is fine', media.allow(other, 1000 + media.MIN_GAP + 1))
ok('the same title needs its own longer gap', not media.allow(info, 1000 + media.MIN_GAP + 1))
media.reset(); t = 10000
n = 0
for i in range(6):
    n += media.allow(info, t); t += media.TITLE_GAP + media.MIN_GAP + 1
ok('at most TITLE_MAX comments about one title', n == media.TITLE_MAX)
ok('prompt: asks for honesty about works she does not know and allows silence', 'не выдумывай' in media.prompt(info) and '[quiet]' in media.prompt(info))
ok('prompt for an ordinary chat is a short hint', 'открыто' in media.prompt(info, first=False))

# the server
import app, character
tmp = pathlib.Path(tempfile.mkdtemp()); character.MEMORY_FILE = tmp / 'memory.json'; app.load_memory()
seen = {}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    seen['last'] = m[-1]['content'] if isinstance(m[-1]['content'], str) else m[-1]['content'][-1]['text']
    yield '[happy] О, это классика!'
app.generate_stream = fake
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8800), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(d):
    r = urllib.request.Request('http://127.0.0.1:8800/chat', json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
media.reset()
c, _ = post({'initiative': 'media', 'window': 'Frieren - AniLibria - Opera'})
ok('media initiative: she is told what is on', c == 200 and 'Frieren' in seen['last'] and 'смотрит аниме' in seen['last'])
seen.clear()
c, _ = post({'initiative': 'media', 'window': 'Frieren - AniLibria - Opera'})
ok('asking again at once: refused, the model is not even called', c == 400 and not seen)
c, _ = post({'initiative': 'media', 'window': 'Re: Счёт за март - Gmail - Google Chrome'})
ok('a non-media title is refused and never reaches the model', c == 400 and not seen)
c, _ = post({'initiative': 'media'})
ok('no title at all: refused', c == 400)
c, _ = post({'message': 'как тебе это?', 'media': 'Stranger Things | Netflix - Google Chrome'})
ok('in a chat: she knows what is on screen', c == 200 and 'Stranger Things' in seen['last'] and 'как тебе это?' in seen['last'])
seen.clear()
c, _ = post({'message': 'привет', 'media': 'Re: Счёт за март - Gmail - Google Chrome'})
ok('a private window title in a chat is ignored', c == 200 and 'Счёт' not in seen['last'])
c, _ = post({'message': 'привет', 'media': 5})
ok('junk media field is harmless', c == 200)
