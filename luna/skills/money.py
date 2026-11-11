"""Exchange rates on request: "100 долларов в вонах", "how much is 50 euro in yen", "100 USD to KRW", "100ドルは何円", "1000원은 몇 엔". Only when he asked in words, and only
with the Actions switch on (it is the same permission as her web search). What leaves the computer is only the three-letter codes and the amount, to the free
rate service of the European Central Bank (frankfurter.app): no key, no account. The program converts and tells her the figure and the date of the rate; she only
retells it. Rubles are not published there, and she says so. In ru, en, ko and ja."""
import json
import re

from luna.hands import netsearch

URL = 'https://api.frankfurter.app/latest?amount=%s&from=%s&to=%s'
CODES = {'USD', 'EUR', 'KRW', 'JPY', 'GBP', 'CNY', 'CHF', 'CAD', 'AUD', 'PLN', 'CZK', 'TRY', 'INR', 'SEK', 'NOK', 'HKD', 'SGD', 'THB', 'BRL', 'MXN', 'ILS', 'ZAR', 'NZD'}
# words per language -> code ("RUB" is known only to be refused honestly)
WORDS = [
    ('USD', r'долл\w*|бакс\w*|dollars?|usd|\$|달러|ドル|米ドル'),
    ('EUR', r'евро|euros?|eur|€|유로|ユーロ'),
    ('KRW', r'вон\w*|won|krw|원|ウォン|₩'),
    ('JPY', r'иен\w*|йен\w*|yen|jpy|엔|円|¥'),
    ('GBP', r'фунт\w* стерлинг\w*|pounds? sterling|gbp|£|파운드 ?스털링|英ポンド|ポンド ?スターリング'),
    ('CNY', r'юан\w*|yuan|cny|rmb|위안|人民元|元'),
    ('CHF', r'франк\w*|swiss francs?|chf|프랑|フラン'),
    ('PLN', r'злот\w*|zlotys?|pln|즈워티|ズウォティ'),
    ('TRY', r'лир\w*|lira|try|리라|リラ'),
    ('RUB', r'рубл\w*|руб\b|rubles?|roubles?|rub|루블|ルーブル'),
]
_ANY = '|'.join('(?P<c%d>%s)' % (i, w) for i, (_, w) in enumerate(WORDS))
_NUM = r'(?P<n>\d[\d ,.]*)'
_CUR = re.compile(r'(?i)' + _ANY)


def parse(text):
    """(amount, from code, to code) or None: a number with a currency, then another currency. A bare "курс доллара" without an amount is not a request here."""
    text = str(text or '')[:200]
    if not re.search(r'(?i)(?:сколько|how much|convert|переведи|конвертируй|курс|몇|얼마|いくら|何|換算|환전|바꿔|両替|в |to |in |into |=|->|は|으로|로|に)', text):
        return None
    m = re.search(_NUM + r'\s*(?:%s)' % _ANY, text, re.I) or re.search(r'(?i)(?:%s)\s*' % _ANY + _NUM, text)
    if not m:
        return None
    try:
        amount = float(re.sub(r'\s', '', m.group('n')).replace(',', '.').rstrip('.'))
    except ValueError:
        return None
    first = next((WORDS[i][0] for i in range(len(WORDS)) if m.group('c%d' % i)), None)
    rest = text[m.end():]
    other = None
    for c in _CUR.finditer(rest):
        code = next((WORDS[i][0] for i in range(len(WORDS)) if c.group('c%d' % i)), None)
        if code and code != first:
            other = code
            break
    if not first or not other or not 0 < amount < 1e12:
        return None
    return amount, first, other


def rate(amount, a, b):
    """The converted amount and the date of the rate as a sentence for her, or '' when the service does not know these currencies. Raises OSError on network trouble."""
    if 'RUB' in (a, b) or a not in CODES or b not in CODES:
        return ''
    status, _, body = netsearch._get(URL % (('%.4f' % amount).rstrip('0').rstrip('.'), a, b), 'application/json')
    if status != 200:
        raise OSError('HTTP %s' % status)
    data = json.loads(body.decode('utf-8', errors='replace'))
    value = data['rates'][b]
    return '%s %s = %s %s (курс Европейского центробанка на %s)' % (_n(amount), a, _n(value), b, data.get('date', '?'))


def _n(x):
    return ('%.2f' % x).rstrip('0').rstrip('.') if abs(x) < 1e9 else '%.4g' % x


def hint(text, allowed):
    """The note for her: the figure, or the honest reason there is none. '' when he did not ask for a conversion."""
    req = parse(text)
    if not req:
        return ''
    amount, a, b = req
    if 'RUB' in (a, b):
        return '[Он просит курс с рублём. Источник программы (Европейский центробанк) рубль не публикует: скажи это честно, цифру из головы не называй.]'
    if not allowed:
        return ('[Он просит перевести валюту. Курсы берутся из интернета, а переключатель «Действия» выключен: скажи, что так сможешь, если он его включит, '
                'и не называй цифру наугад: курсы меняются.]')
    try:
        line = rate(amount, a, b)
    except (OSError, ValueError, KeyError, TypeError):
        return '[Курс получить не удалось (нет сети или сервис не ответил). Скажи это честно и не называй цифру наугад.]'
    if not line:
        return '[Этих валют нет в источнике программы. Скажи это честно, цифру наугад не называй.]'
    return '[Программа посмотрела курс: %s. Назови ему этот результат и дату курса, коротко, своими словами; курсы меняются.]' % line
