"""Counting by the calendar, done by the program: "сколько дней до 1 января", "how many days until Christmas", "크리스마스까지 며칠", "来年の1月1日まであと何日",
"сколько дней между 1 марта и 5 апреля", "через 100 дней какая дата", "what day of the week is March 5", "сколько мне лет, если я родился 12.05.1990".
A language model miscounts days and does not know today's date; the program knows both. When he asks in words (ru, en, ko, ja) it counts and hands her the
real numbers in a bracketed note; she only retells them. Read-only, no files, no network. If the question names no date it can read ("до отпуска"), it stays
silent and leaves the answer to her."""
import calendar
import re
from datetime import date, timedelta

_MON_RU = [('янв', 1), ('фев', 2), ('мар', 3), ('апр', 4), ('мая', 5), ('май', 5), ('июн', 6), ('июл', 7), ('авг', 8), ('сен', 9), ('окт', 10), ('ноя', 11), ('дек', 12)]
_MON_EN = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
_MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
_WEEK = ('понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье')

_RU = r'(?:январ\w*|феврал\w*|март\w*|апрел\w*|ма[яй]\w*|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)'
_EN = r'(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\b\.?'
_PATTERNS = [
    ('iso', re.compile(r'(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)')),
    ('dmy', re.compile(r'(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)')),
    ('ru', re.compile(r'(?i)(?<!\d)(\d{1,2})\s+(%s)(?:\s+(\d{4}))?' % _RU)),
    ('en1', re.compile(r'(?i)\b(%s)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?(?!\d)' % _EN)),
    ('en2', re.compile(r'(?i)(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(%s)(?:,?\s+(\d{4}))?' % _EN)),
    ('ko', re.compile(r'(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일')),
    ('ja', re.compile(r'(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日')),
    ('dm', re.compile(r'(?<![\d.])(\d{1,2})\.(\d{1,2})(?![\d.]\d)(?!\d)')),
]
# named days; the Russian "Рождество" is the Orthodox one (7 January) unless "католическое" is said
_EVENTS = [
    (re.compile(r'(?i)католическ\w+\s+рождеств\w*'), 12, 25, 'католическое Рождество'),
    (re.compile(r'(?i)рождеств\w*'), 1, 7, 'православное Рождество (7 января)'),
    (re.compile(r'(?i)christmas|크리스마스|성탄절|クリスマス'), 12, 25, 'Рождество (25 декабря)'),
    (re.compile(r'(?i)нов\w+\s+год\w*|new year\w*|새해|新年|お正月|元日'), 1, 1, 'Новый год'),
]
_RELATIVE = [
    (re.compile(r'(?i)послезавтра|day after tomorrow|모레|あさって'), 2),
    (re.compile(r'(?i)завтра|tomorrow|내일|明日|あした'), 1),
    (re.compile(r'(?i)сегодня|today|오늘|今日|きょう'), 0),
    (re.compile(r'(?i)вчера|yesterday|어제|昨日|きのう'), -1),
]


def _month_ru(word):
    word = word.lower()
    for stem, n in _MON_RU:
        if word.startswith(stem):
            return n
    return 0


def _find(text, today):
    """Dates named in a piece of text, in order: [(year or None, month, day, note)]; a relative word ("завтра") is a full date."""
    taken, found = [], []

    def free(a, b):
        return all(b <= s or a >= e for s, e in taken)
    for rx, mon, day, note in _EVENTS:
        for m in rx.finditer(text):
            if free(m.start(), m.end()):
                taken.append((m.start(), m.end()))
                found.append((m.start(), None, mon, day, note))
    for kind, rx in _PATTERNS:
        for m in rx.finditer(text):
            if not free(m.start(), m.end()):
                continue
            g = m.groups()
            if kind == 'iso':
                y, mo, d = int(g[0]), int(g[1]), int(g[2])
            elif kind == 'dmy':
                y, mo, d = int(g[2]), int(g[1]), int(g[0])
            elif kind == 'ru':
                y, mo, d = (int(g[2]) if g[2] else None), _month_ru(g[1]), int(g[0])
            elif kind == 'en1':
                y, mo, d = (int(g[2]) if g[2] else None), _MON_EN.get(g[0].lower().rstrip('.')[:3], 0), int(g[1])
            elif kind == 'en2':
                y, mo, d = (int(g[2]) if g[2] else None), _MON_EN.get(g[1].lower().rstrip('.')[:3], 0), int(g[0])
            elif kind in ('ko', 'ja'):
                y, mo, d = (int(g[0]) if g[0] else None), int(g[1]), int(g[2])
            else:
                y, mo, d = None, int(g[1]), int(g[0])
            taken.append((m.start(), m.end()))
            found.append((m.start(), y, mo, d, ''))
    for rx, shift in _RELATIVE:
        for m in rx.finditer(text):
            if free(m.start(), m.end()):
                taken.append((m.start(), m.end()))
                t = today + timedelta(days=shift)
                found.append((m.start(), t.year, t.month, t.day, ''))
    return [f[1:] for f in sorted(found, key=lambda f: f[0])]


def _valid(y, m, d):
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def _resolve(part, today, mode):
    """A named date as a real date. Without a year: 'next' = the nearest one not before today, 'last' = the nearest one not after today, 'this' = this year's."""
    y, m, d, note = part
    if y is not None:
        return date(y, m, d), note
    if mode == 'this':
        return date(today.year, m, d), note
    years = range(today.year, today.year + 9) if mode == 'next' else range(today.year, today.year - 9, -1)
    for year in years:
        if _valid(year, m, d):
            c = date(year, m, d)
            if (mode == 'next' and c >= today) or (mode == 'last' and c <= today):
                return c, note
    raise ValueError('no such date')


def _label(d, note):
    return _shown(d) + (' - ' + note if note else '')


def _shown(d):
    return '%d %s %d (%s)' % (d.day, _MONTHS[d.month - 1], d.year, _WEEK[d.weekday()])


def _plural(n, forms):
    n = abs(n)
    return forms[2] if 11 <= n % 100 <= 14 else forms[0] if n % 10 == 1 else forms[1] if 2 <= n % 10 <= 4 else forms[2]


def _days(n):
    return '%d %s' % (n, _plural(n, ('день', 'дня', 'дней')))


def _span(a, b):
    """Full years, months and days from a to b (a <= b)."""
    years = b.year - a.year
    months = b.month - a.month
    days = b.day - a.day
    if days < 0:
        months -= 1
        prev = b.month - 1 or 12
        days += calendar.monthrange(b.year - (1 if b.month == 1 else 0), prev)[1]
    if months < 0:
        years -= 1
        months += 12
    return years, months, days


def _span_text(a, b):
    y, m, d = _span(a, b)
    parts = []
    if y:
        parts.append('%d %s' % (y, _plural(y, ('год', 'года', 'лет'))))
    if m:
        parts.append('%d %s' % (m, _plural(m, ('месяц', 'месяца', 'месяцев'))))
    if d or not parts:
        parts.append(_days(d))
    return ' '.join(parts)


def _add_months(d, n):
    total = d.year * 12 + d.month - 1 + n
    y, m = divmod(total, 12)
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


# ---- what he asks ----
_BETWEEN = [
    re.compile(r'(?is)\bмежду\s+(?P<a>.+?)\s+и\s+(?P<b>.+)'),
    re.compile(r'(?is)\bbetween\s+(?P<a>.+?)\s+and\s+(?P<b>.+)'),
    re.compile(r'(?is)(?P<a>.+?)\s*(?:부터|에서)\s*(?P<b>.+?)\s*까지\s*(?:며칠|몇 ?일|얼마)'),
    re.compile(r'(?is)(?P<a>.+?)\s*から\s*(?P<b>.+?)\s*まで.{0,6}(?:何日|なんにち)'),
]
_SHIFT = [
    re.compile(r'(?is)(?:какая|какое|какой|что за|узнай|посчитай|скажи).{0,16}(?:дата|число|день недели|день)\b.{0,16}?(?:(?P<fwd>через)\s+(?P<n>\d{1,5})\s*(?P<u>дн\w*|день|недел\w*|месяц\w*|год\w*|лет)|(?P<n2>\d{1,5})\s*(?P<u2>дн\w*|день|недел\w*|месяц\w*|год\w*|лет)\s+(?P<back>назад))'),
    re.compile(r'(?is)(?:через\s+(?P<n>\d{1,5})\s*(?P<u>дн\w*|день|недел\w*|месяц\w*|год\w*|лет)|(?P<n2>\d{1,5})\s*(?P<u2>дн\w*|день|недел\w*|месяц\w*|год\w*|лет)\s+(?P<back>назад))\s*[,:\-—]?\s*(?:какая|какое|какой|что за)?\s*(?:будет\s+|была\s+)?(?:дата|число|день недели)'),
    re.compile(r'(?is)\bwhat\s+(?:date|day)\b.{0,16}?(?:(?P<n>\d{1,5})\s*(?P<u>days?|weeks?|months?|years?)\s*(?P<d>from now|from today|later|ago)|(?:in|after)\s+(?P<n2>\d{1,5})\s*(?P<u2>days?|weeks?|months?|years?))'),
    re.compile(r'(?is)(?P<n>\d{1,5})\s*(?P<u>days?|weeks?|months?|years?)\s*(?P<d>from now|from today|later|ago)\s*[,:\-—]?\s*(?:what|which)\s+(?:date|day)\b'),
    re.compile(r'(?is)(?P<n>\d{1,5})\s*(?P<u>일|주|개월|달|년)\s*(?P<d>후|뒤|전)(?:은|는|의)?\s*.{0,6}(?:날짜|며칠|무슨 요일|몇 월)'),
    re.compile(r'(?is)(?P<n>\d{1,5})\s*(?P<u>日|週間|か月|ヶ月|年)\s*(?P<d>後|前|あと)(?:は|の)?\s*.{0,6}(?:何日|日付|何曜日|いつ)'),
]
_UNTIL = [
    re.compile(r'(?is)\bсколько\s+(?:ещё\s+|еще\s+)?(?:дней|дня|день|недель|месяцев)\s+(?:осталось\s+)?до\s+(?P<x>.+)'),
    re.compile(r'(?is)\bсколько\s+(?:ещё\s+|еще\s+)?(?:осталось|ждать)\s+до\s+(?P<x>.+)'),
    re.compile(r'(?is)\bhow\s+(?:many|long)\b.{0,16}?\b(?:until|till|before|to|left (?:until|till|to))\s+(?P<x>.+)'),
    re.compile(r'(?is)\bdays\s+(?:until|till|left until|left till)\s+(?P<x>.+)'),
    re.compile(r'(?is)(?P<x>.+?)\s*까지\s*(?:며칠|몇 ?일|몇 ?주|얼마나|남았)'),
    re.compile(r'(?is)(?P<x>.+?)\s*まで(?:あと)?\s*(?:何日|なんにち|何週間|どのくらい)'),
]
_AGE = [
    re.compile(r'(?is)\bсколько\s+мне\s+(?:лет|будет\s+лет)\b.{0,24}?(?:родил\w+|рожд\w+|появил\w+)\s*(?:ся|сь)?\s*(?:в\s+|на\s+)?(?P<x>.+)'),
    re.compile(r'(?is)\bсколько\s+лет\b.{0,24}?(?:родил\w+|рожд\w+)\s*(?:ся|сь)?\s*(?:в\s+|на\s+)?(?P<x>.+)'),
    re.compile(r'(?is)\bhow\s+old\b.{0,30}?(?:born|birth)\s*(?:day)?\s*(?:on|in)?\s*(?P<x>.+)'),
    re.compile(r'(?is)(?P<x>.+?)\s*(?:에\s*)?(?:태어났|생일|생이면).{0,10}?(?:몇\s*살|나이)'),
    re.compile(r'(?is)(?P<x>.+?)\s*(?:に)?生まれ.{0,12}?(?:何歳|なんさい|いくつ)'),
]
_SINCE = [
    re.compile(r'(?is)\bсколько\s+(?:дней|дня|день|недель|лет|месяцев|времени)\s+(?:прошло\s+)?(?:с|со)\s+(?P<x>.+)'),
    re.compile(r'(?is)\bhow\s+(?:many|long)\b.{0,16}?\bsince\s+(?P<x>.+)'),
    re.compile(r'(?is)(?P<x>.+?)\s*부터\s*(?:며칠|몇 ?일|얼마나|지났)'),
    re.compile(r'(?is)(?P<x>.+?)\s*から\s*(?:何日|なんにち|どのくらい|経った|たった)'),
]
_WEEKDAY = [
    re.compile(r'(?is)\b(?:какой|какого)\s+(?:день недели|был день|будет день)\s*(?:был\s+|будет\s+)?(?:в\s+|у\s+)?(?P<x>.+)'),
    re.compile(r'(?is)\bwhat\s+day\s+of\s+the\s+week\s+(?:is|was|will be)\s+(?P<x>.+)'),
    re.compile(r'(?is)(?P<x>.+?)\s*(?:은|는|이|가)?\s*무슨\s*요일'),
    re.compile(r'(?is)(?P<x>.+?)\s*(?:は|って)?\s*何曜日'),
]
_UNIT = {'д': 'd', 'де': 'd', 'не': 'w', 'ме': 'm', 'го': 'y', 'ле': 'y', 'da': 'd', 'we': 'w', 'mo': 'm', 'ye': 'y', '일': 'd', '주': 'w', '개': 'm', '달': 'm', '년': 'y',
         '日': 'd', '週': 'w', 'か': 'm', 'ヶ': 'm', '年': 'y'}
_ABOUT = '[Программа посчитала по календарю%s. Сегодня %s. Назови именно эти числа и даты, не пересчитывай и не меняй; перескажи коротко и по-своему.]'


def _kind(unit):
    return _UNIT.get(unit[:2].lower()) or _UNIT.get(unit[:1].lower()) or 'd'


def _shift(today, n, unit, back):
    n = -n if back else n
    kind = _kind(unit)
    if kind == 'd':
        return today + timedelta(days=n)
    if kind == 'w':
        return today + timedelta(weeks=n)
    if kind == 'm':
        return _add_months(today, n)
    try:
        return today.replace(year=today.year + n)
    except ValueError:
        return today.replace(year=today.year + n, day=28)


def _first(rxs, text):
    for rx in rxs:
        m = rx.search(text)
        if m:
            return m
    return None


def handle(text, today=None):
    """The note for her with the real count, or '' when he did not ask a calendar question the program can read."""
    text = ' '.join(str(text or '').split())[:300]
    if not text:
        return ''
    today = today or date.today()
    now = _shown(today)
    try:
        m = _first(_BETWEEN, text)
        if m:
            a, b = _find(m.group('a'), today), _find(m.group('b'), today)
            if a and b:
                da, db = _resolve(a[0], today, 'this')[0], _resolve(b[0], today, 'this')[0]
                if db < da:
                    da, db = db, da
                n = (db - da).days
                return _ABOUT % (': между %s и %s %s (%s)' % (_shown(da), _shown(db), _days(n), _span_text(da, db)), now)
        m = _first(_SHIFT, text)
        if m:
            g = m.groupdict()
            n = g.get('n') or g.get('n2')
            unit = g.get('u') or g.get('u2') or 'д'
            back = bool(g.get('back') or (g.get('d') or '').lower() in ('ago', '전', '前'))
            if n:
                r = _shift(today, int(n), unit, back)
                return _ABOUT % (': %s %s %s = %s' % (n, {'d': 'дн.', 'w': 'нед.', 'm': 'мес.', 'y': 'г.'}[_kind(unit)], 'назад' if back else 'вперёд', _shown(r)), now)
        m = _first(_AGE, text)
        if m:
            parts = _find(m.group('x'), today)
            if parts and parts[0][0] is not None:
                born = _resolve(parts[0], today, 'this')[0]
                if born <= today:
                    nxt = _add_months(born, 12 * (_span(born, today)[0] + 1))
                    return _ABOUT % (': родился %s, сейчас ему %s; следующий день рождения %s, через %s' % (_shown(born), _span_text(born, today), _shown(nxt), _days((nxt - today).days)), now)
        for rxs, mode in ((_WEEKDAY, 'next'),):
            m = _first(rxs, text)
            if m:
                parts = _find(m.group('x'), today)
                if parts:
                    d, note = _resolve(parts[0], today, mode)
                    return _ABOUT % (': %s' % _label(d, note), now)
        m = _first(_UNTIL, text)
        if m:
            parts = _find(m.group('x'), today)
            if parts:
                d, note = _resolve(parts[0], today, 'next')
                n = (d - today).days
                if n == 0:
                    return _ABOUT % (': %s - это сегодня' % _label(d, note), now)
                return _ABOUT % (': до %s осталось %s (%d нед. и %d дн.)' % (_label(d, note), _days(n), n // 7, n % 7), now)
        m = _first(_SINCE, text)
        if m:
            parts = _find(m.group('x'), today)
            if parts:
                d, note = _resolve(parts[0], today, 'last')
                n = (today - d).days
                if n < 0:
                    return ''
                return _ABOUT % (': с %s прошло %s (%s)' % (_label(d, note), _days(n), _span_text(d, today)), now)
    except (ValueError, OverflowError):
        return '[Он назвал дату, которой нет в календаре. Скажи это честно, ничего не считай.]'
    return ''
