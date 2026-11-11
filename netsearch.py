"""Her eyes on the internet: search the web and read a page's text. Read-only; whatever comes back is data for her, never orders.

Only public http(s) addresses are fetched (no localhost, no home network, no credentials in the address, every redirect is checked
again), the answer is size- and time-limited, and only text-like pages are read. Pure standard library; curl.exe is the fallback
where Python's certificate store is out of date (as in character.wiki)."""
import base64
import html
import json
import ipaddress
import re
import socket
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

AGENT = 'Mozilla/5.0 (compatible; LunaCompanion/1.0)'
MAX_BYTES = 600_000
MAX_TEXT = 3500
TIMEOUT = 10
SEARCH_URL = 'https://html.duckduckgo.com/html/?q='

# short names she may open directly, in any of the languages he speaks ("открой гитхаб", "open github", "유튜브 열어줘");
# anything else is looked up with the search and shown to him: she opens it only after he says it is the right one
SITE_NAMES = {
    'https://github.com': 'github гитхаб гитхуб 깃허브 깃헙 ギットハブ',
    'https://store.steampowered.com': 'steam стим стим-магазин 스팀 スチーム',
    'https://www.youtube.com': 'youtube ютуб ютюб 유튜브 ユーチューブ ようつべ',
    'https://www.google.com': 'google гугл 구글 グーグル',
    'https://www.twitch.tv': 'twitch твич 트위치 ツイッチ',
    'https://www.reddit.com': 'reddit реддит 레딧 レディット',
    'https://www.wikipedia.org': 'wikipedia википедия вики 위키백과 위키피디아 ウィキペディア',
    'https://discord.com/app': 'discord дискорд 디스코드 ディスコード',
    'https://x.com': 'twitter твиттер х 트위터 ツイッター',
    'https://web.telegram.org': 'telegram телеграм телега 텔레그램 テレグラム',
    'https://vk.com': 'vk вк вконтакте 브이케이',
    'https://mail.google.com': 'gmail почта джимейл 지메일 ジーメール',
    'https://translate.google.com': 'translate переводчик 번역 구글번역 翻訳 google-translate',
    'https://www.google.com/maps': 'maps карты 지도 구글지도 地図 google-maps',
    'https://stackoverflow.com': 'stackoverflow стековерфлоу 스택오버플로',
    'https://www.pinterest.com': 'pinterest пинтерест 핀터레스트',
    'https://www.netflix.com': 'netflix нетфликс 넷플릭스 ネットフリックス',
    'https://www.instagram.com': 'instagram инстаграм инста 인스타그램 인스타 インスタグラム インスタ',
    'https://www.facebook.com': 'facebook фейсбук 페이스북 フェイスブック',
    'https://www.tiktok.com': 'tiktok тикток 틱톡 ティックトック',
    'https://web.whatsapp.com': 'whatsapp ватсап вотсап 왓츠앱 ワッツアップ',
    'https://www.linkedin.com': 'linkedin линкедин 링크드인',
    'https://www.amazon.com': 'amazon амазон 아마존 アマゾン',
    'https://www.ebay.com': 'ebay ибей 이베이',
    'https://www.aliexpress.com': 'aliexpress алиэкспресс алиэкспрес али 알리익스프레스',
    'https://open.spotify.com': 'spotify спотифай 스포티파이 スポティファイ',
    'https://soundcloud.com': 'soundcloud саундклауд 사운드클라우드',
    'https://yandex.ru': 'yandex яндекс 얀덱스',
    'https://chatgpt.com': 'chatgpt чатгпт 챗gpt 챗지피티 チャットジーピーティー',
    'https://claude.ai': 'claude клод 클로드',
    'https://www.deepl.com/translator': 'deepl дипл 딥엘',
    'https://www.bing.com': 'bing бинг 빙',
    'https://www.naver.com': 'naver 네이버 ネイバー',
    'https://www.daum.net': 'daum даум 다음',
    'https://www.kakaocorp.com': 'kakao какао 카카오',
    'https://www.coupang.com': 'coupang купанг 쿠팡 クーパン',
    'https://namu.wiki': 'namuwiki namu 나무위키',
    'https://www.nicovideo.jp': 'niconico ニコニコ ニコニコ動画 니코니코',
    'https://www.pixiv.net': 'pixiv пиксив ピクシブ 픽시브',
    'https://www.yahoo.co.jp': 'yahoo ヤフー 야후',
    'https://www.rakuten.co.jp': 'rakuten 라쿠텐 楽天',
    'https://line.me': 'line 라인 ライン',
    'https://www.crunchyroll.com': 'crunchyroll кранчиролл 크런치롤',
    'https://www.epicgames.com': 'epicgames эпик epic 에픽게임즈 에픽',
    'https://www.roblox.com': 'roblox роблокс 로블록스',
    'https://www.minecraft.net': 'minecraft майнкрафт 마인크래프트 マインクラフト',
    'https://godotengine.org': 'godot годот 고도',
    'https://unity.com': 'unity юнити 유니티',
    'https://www.unrealengine.com': 'unreal анриал 언리얼 アンリアル',
    'https://www.blender.org': 'blender блендер 블렌더',
    'https://www.python.org': 'python питон 파이썬',
    'https://developer.mozilla.org': 'mdn',
}
SITES = {name: url for url, names in SITE_NAMES.items() for name in names.split()}
SITE_FILLER = re.compile(r'(?i)^(?:the|сайт|сайта|сайт\s+на|site|website|web\s*site|страницу|страница|사이트|웹사이트|サイト|ホームページ)\s+|\s+(?:сайт|site|website|사이트|웹사이트|サイト|в\s+браузере|in\s+the\s+browser|브라우저에서)$')


def site_key(what):
    """A site name as typed by a person: lowercase, no quotes, no filler words (сайт / site / 사이트), no www."""
    key = ' '.join(str(what or '').split()).strip(' .!?,"\'«»“”').lower()
    for _ in range(2):
        key = SITE_FILLER.sub('', key).strip()
    key = re.sub(r'^www\.', '', key)
    key = re.sub(r'(?:을|를|으로|로|에|이|가|은|는)$', '', key) if re.search('[가-힯]', key) and key not in SITES else key   # Korean particles
    return key


def known_site(what):
    """(url, label) when it is a name we know or a public address, else None (then she searches and asks)."""
    what = ' '.join(str(what or '').split())[:160]
    key = site_key(what)
    if key in SITES:
        return SITES[key], what
    url = public_url(what)
    if url:
        return url, urlparse(url).hostname
    return None


DOMAIN_RE = re.compile(r'^(?:https?://)?([a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+)(?::\d{2,5})?(?:[/?#]\S*)?$', re.I)


def public_url(url):
    """The address cleaned up (https:// added when missing) if it points to a public website, else None."""
    url = str(url or '').strip().strip('<>"\'')
    if not 4 <= len(url) <= 500 or re.search(r'[\s\x00-\x1f]', url):
        return None
    if not re.match(r'^https?://', url, re.I):
        if '://' in url or not DOMAIN_RE.match(url):
            return None
        url = 'https://' + url
    parts = urlparse(url)
    host = parts.hostname
    if parts.scheme not in ('http', 'https') or not host or parts.username or parts.password:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    if port not in (None, 80, 443, 8080, 8443):
        return None
    if not _public_host(host):
        return None
    return url


def _public_host(host):
    host = host.strip('[]').lower()
    if host in ('localhost', '') or host.endswith(('.localhost', '.local', '.internal', '.lan', '.home', '.corp')):
        return False
    try:
        addrs = {ipaddress.ip_address(host)}
    except ValueError:
        if '.' not in host:
            return False
        try:
            addrs = {ipaddress.ip_address(i[4][0]) for i in socket.getaddrinfo(host, None)}
        except (OSError, ValueError):
            return False
    return bool(addrs) and all(a.is_global for a in addrs)


def resolve_site(what):
    """What she wants opened -> (url, label) when it is a known name or a public address, else None (see site_candidates)."""
    what = ' '.join(str(what or '').split())[:160]
    return known_site(what) if what else None


def site_candidates(what, limit=3):
    """Sites found by searching for a name nobody listed -> [(url, title)], one per website, best first. Never an address of
    this computer: an address is not turned into a search, and the results are public hosts only."""
    what = ' '.join(str(what or '').split())[:160]
    if not what or '://' in what or DOMAIN_RE.match(what):
        return []
    try:
        hits = search(site_key(what) or what, limit * 3)
    except (OSError, ValueError, subprocess.SubprocessError):
        hits = []
    out, hosts = [], set()
    for h in hits:
        host = urlparse(h['url']).hostname or ''
        if host in hosts:
            continue
        hosts.add(host)
        out.append((h['url'], h['title'][:80] or host))
        if len(out) >= limit:
            break
    return out


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _get(url, accept='text/html,text/plain,application/xhtml+xml'):
    """One hop, no redirects followed -> (status, headers, bytes). Falls back to curl when the certificate store is stale."""
    req = Request(url, headers={'User-Agent': AGENT, 'Accept': accept, 'Accept-Language': 'ru,en;q=0.8'})
    try:
        with build_opener(_NoRedirect).open(req, timeout=TIMEOUT) as r:
            return r.status, r.headers, r.read(MAX_BYTES)
    except HTTPError as e:
        return e.code, e.headers, b''
    except URLError as e:
        if 'CERTIFICATE_VERIFY_FAILED' not in str(e):
            raise OSError(str(e.reason))
    done = subprocess.run(['curl', '-s', '-m', str(TIMEOUT), '-A', AGENT, '--max-filesize', str(MAX_BYTES), '-D', '-', url], capture_output=True, timeout=TIMEOUT + 5)
    head, _, body = done.stdout.partition(b'\r\n\r\n')
    while head.startswith(b'HTTP/') and body.startswith(b'HTTP/'):   # curl prints interim headers first
        head, _, body = body.partition(b'\r\n\r\n')
    lines = head.decode('latin-1').split('\r\n')
    status = int(lines[0].split()[1]) if lines and len(lines[0].split()) > 1 else 0
    headers = {k.strip().lower(): v.strip() for k, _, v in (l.partition(':') for l in lines[1:])}

    class H(dict):
        def get(self, k, d=None):
            return dict.get(self, k.lower(), d)
    return status, H(headers), body[:MAX_BYTES]


def fetch(url):
    """The page at a public address as readable text (cut), following at most 4 redirects, each one checked. Raises OSError/ValueError."""
    for _ in range(5):
        url = public_url(url)
        if not url:
            raise ValueError('address')
        status, headers, body = _get(url)
        if status in (301, 302, 303, 307, 308) and headers.get('Location'):
            url = urljoin(url, headers.get('Location'))
            continue
        if status != 200:
            raise OSError('HTTP %s' % status)
        kind = (headers.get('Content-Type') or 'text/html').lower()
        if not ('text/' in kind or 'xml' in kind or 'json' in kind):
            raise ValueError('type')
        m = re.search(r'charset=([\w-]+)', kind)
        try:
            text = body.decode(m.group(1) if m else 'utf-8', errors='replace')
        except LookupError:
            text = body.decode('utf-8', errors='replace')
        return page_text(text)
    raise OSError('redirects')


def page_text(raw):
    """HTML -> plain text: no scripts, styles or markup; whitespace squeezed; cut to MAX_TEXT."""
    raw = re.sub(r'(?is)<(script|style|noscript|svg|head|nav|footer|form|iframe)\b.*?</\1\s*>', ' ', raw)
    raw = re.sub(r'(?is)<!--.*?-->', ' ', raw)
    raw = re.sub(r'(?i)</?(p|div|br|li|tr|h[1-6]|section|article)\b[^>]*>', '\n', raw)
    raw = re.sub(r'(?s)<[^>]*>', ' ', raw)
    text = html.unescape(raw)
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n', text).strip()
    return text[:MAX_TEXT]


def search(query, limit=4):
    """Web search -> [{'title','url','snippet'}], best first. Raises OSError if the search page cannot be reached."""
    query = ' '.join(str(query or '').split())[:160]
    if not query:
        return []
    try:
        status, headers, body = _get(SEARCH_URL + quote_plus(query))
    except (OSError, subprocess.SubprocessError):
        status, body = 0, b''
    out = _parse_results(body.decode('utf-8', errors='replace'), limit) if status == 200 else []
    if not out:   # DuckDuckGo asks for a human check (a bot test is never bypassed): another ordinary search page, then the encyclopedia
        try:
            status, headers, body = _get(BING_URL + quote_plus(query))
        except (OSError, subprocess.SubprocessError):
            status, body = 0, b''
        out = _parse_bing(body.decode('utf-8', errors='replace'), limit) if status == 200 else []
    return out or wiki_search(query, limit)


def wiki_search(query, limit=4):
    """Wikipedia's own search API (the language follows the script of the question) -> the same result list."""
    langs = ['ru', 'en'] if re.search('[а-яё]', query.lower()) else ['ja', 'en'] if re.search('[぀-ヿ一-鿿]', query) else ['ko', 'en'] if re.search('[가-힯]', query) else ['en', 'ru']
    out = []
    for lang in langs:
        try:
            status, headers, body = _get('https://%s.wikipedia.org/w/api.php?action=query&list=search&srlimit=%d&format=json&srsearch=%s' % (lang, limit, quote_plus(query)), 'application/json')
            rows = json.loads(body.decode('utf-8', errors='replace'))['query']['search'] if status == 200 else []
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            continue
        for r in rows:
            out.append({'title': r['title'][:120], 'url': 'https://%s.wikipedia.org/wiki/%s' % (lang, quote_plus(r['title'].replace(' ', '_'), safe='_()')),
                        'snippet': html.unescape(re.sub(r'<[^>]+>', '', r.get('snippet', '')))[:240]})
        if len(out) >= limit:
            break
    return out[:limit]


def wiki_text(url):
    """The introduction of a Wikipedia article as plain text, '' if it is not one."""
    m = re.match(r'https://(\w+)\.wikipedia\.org/wiki/([^?#]+)', url)
    if not m:
        return ''
    try:
        status, headers, body = _get('https://%s.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&explaintext=1&format=json&titles=%s' % (m.group(1), m.group(2)), 'application/json')
        pages = json.loads(body.decode('utf-8', errors='replace'))['query']['pages']
        return next(iter(pages.values())).get('extract', '')[:MAX_TEXT]
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return ''


BING_URL = 'https://www.bing.com/search?q='


def _parse_bing(text, limit):
    """Bing result blocks -> [{'title','url','snippet'}]; its links are redirects that carry the real address (base64) in u=."""
    out = []
    for m in re.finditer(r'(?is)<li class="b_algo"[^>]*>(.*?)</li>', text):
        block = m.group(1)
        a = re.search(r'(?is)<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block)
        if not a:
            continue
        href = html.unescape(a.group(1))
        q = parse_qs(urlparse(href).query)
        if 'u' in q and q['u'][0][:2] == 'a1':
            try:
                raw = q['u'][0][2:]
                href = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)).decode('utf-8')
            except (ValueError, UnicodeDecodeError):
                continue
        url = public_url(href)
        if not url or urlparse(url).hostname.endswith('bing.com'):
            continue
        snippet = re.search(r'(?is)<p[^>]*>(.*?)</p>', block)
        out.append({'title': html.unescape(re.sub(r'<[^>]+>', '', a.group(2))).strip()[:120], 'url': url,
                    'snippet': html.unescape(re.sub(r'<[^>]+>', '', snippet.group(1))).strip()[:240] if snippet else ''})
        if len(out) >= limit:
            break
    return out


def _parse_results(text, limit):
    out = []
    for m in re.finditer(r'(?is)<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|\Z)', text):
        href = html.unescape(m.group(1))
        if href.startswith('//'):
            href = 'https:' + href
        q = parse_qs(urlparse(href).query)
        if 'uddg' in q:
            href = q['uddg'][0]
        url = public_url(href)
        if not url or urlparse(url).hostname.endswith('duckduckgo.com'):
            continue
        title = html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip()
        s = re.search(r'(?is)class="result__snippet"[^>]*>(.*?)</a>', m.group(3))
        snippet = html.unescape(re.sub(r'<[^>]+>', '', s.group(1))).strip() if s else ''
        out.append({'title': title[:120], 'url': url, 'snippet': snippet[:240]})
        if len(out) >= limit:
            break
    return out


def research(query, pages=2):
    """Search, then read the best pages -> text for her (marked as untrusted data) or '' when nothing was found."""
    try:
        hits = search(query, 4)
    except (OSError, ValueError, subprocess.SubprocessError):
        return ''
    if not hits:
        return ''
    parts = []
    for n, hit in enumerate(hits):
        block = '[%d] %s (%s)\n%s' % (n + 1, hit['title'], urlparse(hit['url']).hostname, hit['snippet'])
        if n < pages:
            try:
                block += '\n' + (wiki_text(hit['url']) if '.wikipedia.org/' in hit['url'] else fetch(hit['url']))[:1500]
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
        parts.append(block)
    return '\n\n'.join(parts)
