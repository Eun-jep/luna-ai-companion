"""His lists: a shopping list and a to-do list she keeps for him. "add milk to the shopping list", "добавь хлеб в список покупок", "장보기 목록에 우유 추가",
"買い物リストに牛乳を追加". The program reads the request, changes the list and tells her what it did; she only retells it. Everything stays in lists.json
next to the program (nothing is sent anywhere). Adding, removing one item and reading the list are done at once because he asked in words; wiping a whole
list is NOT done by her: she says so and he removes the items himself. In ru, en, ko and ja."""
import paths
import json
import os
import re
import threading

MAX_ITEMS = 60         # in one list
MAX_ADD = 8            # items in one request
MAX_LEN = 60           # characters of an item


def _file():
    return paths.data_file('lists.json')


FILE = _file()
_lock = threading.RLock()
NAMES = {'shop': 'список покупок', 'todo': 'список дел'}

# which list: the word before or after "list"
_SHOP = r'(?:покупок|продукт\w*|магазин\w*|shopping|grocer(?:y|ies)|장보기|쇼핑|마트|買い物|買物|ショッピング)'
_TODO = r'(?:дел|задач|to-?do|todo|tasks?|할 ?일|해야 ?할 ?일|やること|ToDo|タスク|やることリスト)'
_LIST = r'(?:список\w*|лист\w*|list|목록|리스트|リスト)'
_ANYLIST = r'(?:%s\s+%s|%s\s*%s|%s)' % (_LIST, _SHOP, _SHOP, _LIST, _LIST)

# one request per language: the group "what" is the item(s), the group "which" is the list word (maybe empty)
_ADD = [
    re.compile(r'(?is)\b(?:добавь|запиши|внеси|занеси|положи|впиши|поставь)\s+(?P<what>.+?)\s+(?:в|на)\s+(?:мой\s+|наш\s+|общий\s+)?(?:список|лист)\s*(?P<which>%s|%s)?' % (_SHOP, _TODO)),
    re.compile(r'(?is)\b(?:добавь|запиши|внеси|занеси|положи|впиши)\s+(?:в|на)\s+(?:мой\s+|наш\s+)?(?:список|лист)\s*(?P<which>%s|%s)?\s*[:,\-—]?\s*(?P<what>.+)' % (_SHOP, _TODO)),
    re.compile(r'(?is)\b(?:add|put|write down)\s+(?P<what>.+?)\s+(?:to|on|onto|in)\s+(?:my\s+|the\s+|our\s+)?(?P<which>%s|%s)?\s*list\b' % (_SHOP, _TODO)),
    re.compile(r'(?is)\b(?:add|put)\s+to\s+(?:my\s+|the\s+|our\s+)?(?P<which>%s|%s)?\s*list\s*[:,\-—]?\s*(?P<what>.+)' % (_SHOP, _TODO)),
    re.compile(r'(?is)(?P<which>%s)?\s*(?:목록|리스트|%s)\s*에\s*(?P<what>.+?)\s*(?:을|를)?\s*(?:추가|넣어|적어|써|올려)' % (_SHOP + '|' + _TODO, _LIST)),
    re.compile(r'(?is)(?P<what>.+?)\s*(?:을|를)\s*(?P<which>%s|%s)?\s*(?:목록|리스트)\s*에\s*(?:추가|넣어|적어|써|올려)' % (_SHOP, _TODO)),
    re.compile(r'(?is)(?P<which>%s|%s)?\s*(?:リスト)\s*に\s*(?P<what>.+?)\s*を?\s*(?:追加|入れて|書いて|足して|加えて)' % (_SHOP, _TODO)),
    re.compile(r'(?is)(?P<what>.+?)\s*を\s*(?P<which>%s|%s)?\s*(?:リスト)\s*に\s*(?:追加|入れて|書いて|足して|加えて)' % (_SHOP, _TODO)),
]
_DEL = [
    re.compile(r'(?is)\b(?:убери|удали|вычеркни|выкинь|сотри)\s+(?P<what>.+?)\s+из\s+(?:моего\s+|нашего\s+)?(?:списка|листа)\s*(?P<which>%s|%s)?' % (_SHOP, _TODO)),
    re.compile(r'(?is)\b(?:remove|delete|cross off|take)\s+(?P<what>.+?)\s+(?:from|off|out of)\s+(?:my\s+|the\s+|our\s+)?(?P<which>%s|%s)?\s*list\b' % (_SHOP, _TODO)),
    re.compile(r'(?is)(?P<what>.+?)\s*(?:을|를)\s*(?P<which>%s|%s)?\s*(?:목록|리스트)\s*에서\s*(?:빼|지워|삭제|제거)' % (_SHOP, _TODO)),
    re.compile(r'(?is)(?P<what>.+?)\s*を\s*(?P<which>%s|%s)?\s*(?:リスト)\s*から\s*(?:消して|削除|外して|取って|省いて)' % (_SHOP, _TODO)),
]
_SHOW = [
    re.compile(r'(?i)(?:что|чего|какой|какие|покажи|прочитай|зачитай|скажи|назови|открой).{0,24}?(?:(?:в|на)\s+(?:моём\s+|моем\s+|нашем\s+)?(?:списке|листе)|(?:список|лист)\s*(?P<which>%s|%s))' % (_SHOP, _TODO)),
    re.compile(r'(?i)(?:show|read|open|what.?s (?:on|in)|what is (?:on|in)|tell me).{0,20}?\b(?:my |the |our )?(?P<which>%s|%s)?\s*list\b' % (_SHOP, _TODO)),
    re.compile(r'(?i)(?P<which>%s|%s)?\s*(?:목록|리스트).{0,10}?(?:보여|알려|읽어|뭐|뭔지|열어)' % (_SHOP, _TODO)),
    re.compile(r'(?i)(?P<which>%s|%s)?\s*(?:リスト)\s*(?:を|は|に何).{0,6}?(?:見せて|教えて|読んで|何|開いて)' % (_SHOP, _TODO)),
]
_WIPE = re.compile(r'(?i)(?:очисти|сотри|удали|обнули|выбрось)\s+(?:весь\s+|всё\s+|все\s+)?(?:мой\s+)?(?:список|лист)|(?:clear|wipe|empty|delete)\s+(?:all of\s+|the whole\s+|my\s+|the\s+)?(?:\w+\s+)?list|(?:목록|리스트).{0,6}(?:전부|모두|다)?\s*(?:지워|비워|삭제)|リスト(?:を)?(?:全部|すべて|全て)?(?:消して|空に|削除)')

_SPLIT = re.compile(r'\s*(?:,|;|、|，|\band\b|\bи\b|\bа также\b|\+|와|과|그리고|と(?=[^\s])|\n)\s*', re.I)
_TRIM = re.compile(r'(?i)^\s*(?:please|пожалуйста|ещё|еще|also|a\s+|an\s+|the\s+)?\s*|\s*(?:please|пожалуйста|пожалуйста\.|,)?\s*[.!?。！？]*\s*$')


def _kind(text, word):
    """Which list: the word named in the request; "покупок" and friends mean the shopping list, "дел" and friends the to-do list, and without a word
    the shopping list when the items look like goods is not guessed: the default is the to-do list only if it has no shopping word anywhere."""
    for probe in (word, text):
        if probe and re.search(_TODO, str(probe), re.I) and not re.search(_SHOP, str(probe), re.I):
            return 'todo'
        if probe and re.search(_SHOP, str(probe), re.I):
            return 'shop'
    return 'shop'


def _items(what):
    out = []
    for part in _SPLIT.split(str(what or '')):
        part = _TRIM.sub('', part).strip(' "«»\'')
        if part and not re.fullmatch(r'[\W\d_]+', part):
            out.append(part[:MAX_LEN])
    seen, unique = set(), []
    for item in out:
        if item.lower() not in seen:
            seen.add(item.lower())
            unique.append(item)
    return unique[:MAX_ADD]


def load():
    with _lock:
        try:
            data = json.loads(FILE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
    clean = {}
    for key in ('shop', 'todo'):
        items = data.get(key) if isinstance(data, dict) else None
        clean[key] = [str(i)[:MAX_LEN] for i in items if isinstance(i, str) and i.strip()][:MAX_ITEMS] if isinstance(items, list) else []
    return clean


def _save(data):
    with _lock:
        try:
            tmp = FILE.with_suffix('.tmp')
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
            os.replace(tmp, FILE)
            return True
        except OSError:
            return False


def wants(text):
    text = str(text or '')
    return bool(any(rx.search(text) for rx in _ADD + _DEL + _SHOW) or _WIPE.search(text))


def parse(text):
    """('add' | 'del' | 'show' | 'wipe', list kind, [items]) or None. A plain mention of a list is not a request."""
    text = str(text or '').strip()
    if not text or len(text) > 400:
        return None
    if _WIPE.search(text):
        return 'wipe', _kind(text, ''), []
    for action, rxs in (('del', _DEL), ('add', _ADD), ('show', _SHOW)):
        for rx in rxs:
            m = rx.search(text)
            if not m:
                continue
            which = m.groupdict().get('which') or ''
            if action == 'show':
                return 'show', _kind(text, which), []
            items = _items(m.group('what'))
            if items and not any(re.fullmatch(_ANYLIST, i, re.I) for i in items):
                return action, _kind(text, which), items
    return None


def apply(request):
    """Do what parse() read; returns the hint for her (what the program did, and the list as it stands), or '' for nothing to say."""
    if not request:
        return ''
    action, kind, items = request
    name = NAMES[kind]
    data = load()
    mine = data[kind]
    if action == 'wipe':
        return ('[Он просит очистить весь %s. Целиком списки ты не стираешь: скажи об этом коротко и по-доброму и предложи убрать по одному пункту, '
                'назвав его. Сейчас в списке: %s.]' % (name, '; '.join(mine) or 'пусто'))
    if action == 'show':
        return ('[Программа открыла его %s: %s. Прочти ему список как есть, ничего не добавляя и не убирая от себя.]'
                % (name, '; '.join('%d) %s' % (i + 1, t) for i, t in enumerate(mine)) if mine else 'он пока пуст'))
    if action == 'add':
        added, dup = [], []
        for item in items:
            if item.lower() in (t.lower() for t in mine):
                dup.append(item)
            elif len(mine) < MAX_ITEMS:
                mine.append(item)
                added.append(item)
        if added and not _save(data):
            return '[Программа не смогла записать %s на диск. Скажи ему честно, что не записала.]' % name
        if not added and len(mine) >= MAX_ITEMS:
            return '[%s переполнен (%d пунктов), новое не записано. Скажи ему об этом.]' % (name.capitalize(), MAX_ITEMS)
        say = ('[Программа добавила в %s: %s.' % (name, '; '.join(added))) if added else '[Ничего нового не добавлено'
        if dup:
            say += ' Уже было в списке: %s.' % '; '.join(dup)
        return say + ' Скажи ему коротко, что записала, по-своему. Пунктов в списке: %d.]' % len(mine)
    gone, missing = [], []
    for item in items:
        hit = next((t for t in mine if t.lower() == item.lower()), None) or next((t for t in mine if item.lower() in t.lower() and len(item) >= 3), None)
        if hit:
            mine.remove(hit)
            gone.append(hit)
        else:
            missing.append(item)
    if gone and not _save(data):
        return '[Программа не смогла сохранить %s. Скажи ему честно.]' % name
    say = ('[Программа убрала из %s: %s.' % (name, '; '.join(gone))) if gone else '[Ничего не убрано'
    if missing:
        say += ' Такого пункта нет: %s.' % '; '.join(missing)
    return say + ' Скажи ему коротко, что сделано. Пунктов осталось: %d.]' % len(mine)


def handle(text):
    """parse + apply in one step for the chat: the hint to add to her prompt, '' when the message is not a list request."""
    return apply(parse(text))
