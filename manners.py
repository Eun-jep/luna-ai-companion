"""His own requests about how she talks to him: "говори короче", "не шути", "объясни проще", "называй меня Вадим", "отвечай по-английски", "keep it short", "call me Vadim",
"더 짧게 말해", "冗談はやめて", ... in ru/en/ko/ja. A request with a standing word ("всегда", "from now on", "앞으로", "これから") is kept in manners.json and reminded to her in every turn until he
says "говори как обычно" / "back to normal" / "원래대로" / "いつも通りに"; without it the request holds for this reply only, so one "объясни простыми словами" does not rewrite her for good.
A nickname is always kept (that is what asking for one means). Nothing here makes her colder: it is his steering of her manner, and her own character stays under it.
Only his own words count: the app never calls this for text that came from the internet."""
import paths
import json
import os
import re
import threading


def _file():
    return paths.data_file('manners.json')


FILE = _file()
_lock = threading.RLock()
KEYS = ('length', 'jokes', 'simple', 'lang', 'name')
LANGS = {'ru': 'по-русски', 'en': 'по-английски', 'ko': 'по-корейски', 'ja': 'по-японски'}

_STAND = re.compile(r'(?i)всегда|теперь|впредь|с\s+этого\s+момента|отныне|always|from\s+now\s+on|going\s+forward|앞으로|항상|이제부터|これから|いつも|今後|ずっと')
_RESET = re.compile(r'(?i)говори\s+как\s+обычно|веди\s+себя\s+как\s+обычно|вернись\s+к\s+обычн\w+|сбрось\s+(?:стиль|манеру|настройки\s+общения)|(?:back\s+to|return\s+to)\s+normal|talk\s+normally|'
                    r'reset\s+(?:your\s+)?(?:style|manner|tone)|원래대로\s*(?:말해|해)?|평소처럼|いつも通り(?:に|で)?|元に戻して|普通に話して')
_SHORT = re.compile(r'(?i)(?:отвечай|говори|пиши|ответь|скажи)\s+(?:мне\s+)?(?:покороче|короче|кратко|лаконичнее)|покороче|без\s+воды|keep\s+it\s+(?:short|brief)|be\s+(?:brief|concise|shorter)|'
                    r'shorter\s+(?:answers|replies)|짧게\s*(?:말해|답해|대답해)|간단(?:히|하게)\s*말해|もっと短く|短めに|簡潔に')
_LONG = re.compile(r'(?i)(?:отвечай|говори|пиши|расскажи|ответь)\s+(?:мне\s+)?(?:подробнее|поподробнее|развёрнуто|развернуто|длиннее)|more\s+detail|longer\s+(?:answers|replies)|elaborate\s+more|'
                   r'(?:더\s*)?자세히\s*(?:말해|답해|설명해)|もっと詳しく|詳しく(?:話して|答えて)')
_NOJOKE = re.compile(r'(?i)не\s+шути|без\s+шуто[кч]|хватит\s+шутить|перестань\s+шутить|(?:don.?t|do\s+not|stop)\s+(?:joke|joking)|no\s+jokes|농담\s*(?:하지\s*마|그만)|冗談(?:は)?(?:やめて|禁止|なしで)')
_MOREJOKE = re.compile(r'(?i)шути\s+(?:больше|чаще|побольше)|больше\s+шуток|joke\s+more|more\s+jokes|농담\s*(?:많이|더)\s*해|もっと冗談|冗談を(?:もっと)?言って')
_SIMPLE = re.compile(r'(?i)объясни\s+(?:проще|попроще|как\s+ребёнку|как\s+ребенку)|(?:говори|объясняй|отвечай)\s+(?:проще|попроще)|простыми\s+словами|explain\s+(?:it\s+)?(?:simply|simpler)|'
                     r'explain\s+(?:it\s+)?like\s+i.?m\s+(?:5|five)|in\s+simple\s+terms|쉽게\s*(?:설명|말)|簡単に(?:説明|言って)|やさしく説明|わかりやすく')
_LANG = re.compile(r'(?i)(?:отвечай|говори|пиши)\s+(?:мне\s+)?по[- ](английски|корейски|японски|русски)|(?:answer|reply|speak|talk|write)\s+(?:to\s+me\s+)?in\s+(english|korean|japanese|russian)|'
                   r'(영어|한국어|일본어|러시아어)로\s*(?:말해|답해|대답해)|(英語|韓国語|日本語|ロシア語)で(?:話して|答えて|返事して|書いて)')
_LANGKEY = {'английски': 'en', 'english': 'en', '영어': 'en', '英語': 'en', 'корейски': 'ko', 'korean': 'ko', '한국어': 'ko', '韓国語': 'ko',
            'японски': 'ja', 'japanese': 'ja', '일본어': 'ja', '日本語': 'ja', 'русски': 'ru', 'russian': 'ru', '러시아어': 'ru', 'ロシア語': 'ru'}
_NAME = re.compile(r'(?i)(?:называй|зови)\s+меня\s+([^\W\d_][^\W\d_\-]{0,22}(?:-[^\W\d_]{1,12})?)(?![^\W\d_])|call\s+me\s+([A-Za-z][A-Za-z\-]{0,22})(?![A-Za-z])|'
                   r'(?:내|나를)\s*(?:이름은\s*)?([가-힣A-Za-z]{1,10}?)(?:라고|이라고)\s*불러|([぀-ヿ一-鿿A-Za-z]{1,10}?)(?:と|って)呼んで')
_NOT_NAMES = {'пожалуйста', 'пж', 'как', 'так', 'теперь', 'всегда', 'иначе', 'просто', 'please', 'always', 'now', 'something', 'whatever', 'later', 'again', 'by', 'what', 'how', 'when', 'когда', 'если', 'потом', 'завтра', 'вечером', 'утром', 'сегодня', 'обратно', 'на', 'в', 'к', 'не', 'и', 'тогда', 'что', 'чтобы', 'if',
              'tomorrow', 'tonight', 'back', 'then'}


def parse(text):
    """{'reset': bool, 'stand': bool, 'set': {key: value}} from one message, or None when he asked nothing about her manner."""
    text = str(text or '')[:300]
    if not text.strip():
        return None
    stand = bool(_STAND.search(text))
    if _RESET.search(text):
        return {'reset': True, 'stand': True, 'set': {}}
    out = {}
    if _NOJOKE.search(text):
        out['jokes'] = 'off'
    elif _MOREJOKE.search(text):
        out['jokes'] = 'more'
    if _SHORT.search(text):
        out['length'] = 'short'
    elif _LONG.search(text):
        out['length'] = 'long'
    if _SIMPLE.search(text):
        out['simple'] = 'on'
    m = _LANG.search(text)
    if m:
        word = next(g for g in m.groups() if g).lower()
        out['lang'] = _LANGKEY.get(word) or _LANGKEY.get(next(g for g in m.groups() if g))
    m = _NAME.search(text)
    if m:
        name = next(g for g in m.groups() if g).strip(' -')
        if name and name.lower() not in _NOT_NAMES and len(name) <= 24:
            out['name'] = name[:1].upper() + name[1:]
    if not out:
        return None
    return {'reset': False, 'stand': stand, 'set': {k: v for k, v in out.items() if v}}


def load():
    with _lock:
        try:
            data = json.loads(FILE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
    return {k: str(data[k]) for k in KEYS if isinstance(data.get(k), str) and data[k]}


def _save(data):
    with _lock:
        tmp = FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps({k: data[k] for k in KEYS if k in data}, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, FILE)


_TEXT = {('length', 'short'): 'отвечать короче, одной-двумя фразами, без лишних подробностей',
         ('length', 'long'): 'отвечать подробнее и развёрнуто',
         ('jokes', 'off'): 'не шутить и не подкалывать (серьёзный, спокойный тон; тепло остаётся)',
         ('jokes', 'more'): 'шутить чаще и смелее',
         ('simple', 'on'): 'объяснять проще, простыми словами и бытовыми примерами, без терминов'}


def _describe(settings):
    parts = []
    for key, val in settings.items():
        if key == 'lang':
            parts.append('отвечать %s' % LANGS.get(val, val))
        elif key == 'name':
            parts.append('называть его «%s» (естественно, не в каждой фразе)' % val)
        elif (key, val) in _TEXT:
            parts.append(_TEXT[(key, val)])
    return '; '.join(parts)


def handle(text):
    """Applies his request (keeping standing ones) and returns the note for her: what changed, or '' when he asked nothing about her manner."""
    req = parse(text)
    if not req:
        return ''
    if req['reset']:
        keep = {k: v for k, v in load().items() if k == 'name'}
        had = load()
        _save(keep)
        return ('[Он просит говорить как обычно: все его прежние просьбы о манере (%s) сняты, кроме имени, как он просил себя называть. Подтверди коротко и вернись к себе обычной.]'
                % (_describe({k: v for k, v in had.items() if k != 'name'}) or 'их и не было'))
    settings = req['set']
    keep = {k: v for k, v in settings.items() if k == 'name' or req['stand']}
    if keep:
        data = load()
        data.update(keep)
        if keep.get('jokes') == 'off':
            pass
        _save(data)
    now = _describe(settings)
    if req['stand'] or 'name' in settings:
        kept = _describe({k: v for k, v in settings.items() if k in keep})
        extra = (' Только эту просьбу про одну реплику: %s.' % _describe({k: v for k, v in settings.items() if k not in keep})) if len(keep) < len(settings) else ''
        return ('[Он просит поменять манеру общения: %s. Это запомнено надолго, пока он не скажет «говори как обычно».%s Подтверди коротко и по-своему и сразу веди себя так.]' % (kept or now, extra))
    return ('[Он просит на этот ответ: %s. Это только для этой реплики, не навсегда. Исполни без обсуждений.]' % now)


def standing():
    """The reminder put next to every message while some request of his is kept; '' when there is none."""
    data = load()
    if not data:
        return ''
    return ('[Его постоянные просьбы о манере общения (он сам их попросил, они действуют, пока он не скажет «говори как обычно»): %s. Следуй им без напоминаний; '
            'твой характер от этого не исчезает, меняется только манера.]' % _describe(data))
