"""Exact arithmetic for her: a language model counts by feel and is wrong about long numbers, percentages and dates, so she hands
the sum to the program with [calc:expression] and only retells the result. Read-only: nothing here touches files, the network or eval."""
import ast
import datetime
import math
import operator
import re

BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
UN = {ast.USub: operator.neg, ast.UAdd: operator.pos}
FUNCS = {'sqrt': math.sqrt, 'abs': abs, 'round': round, 'min': min, 'max': max, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
         'ln': math.log, 'log': math.log10, 'log10': math.log10, 'log2': math.log2, 'exp': math.exp, 'floor': math.floor,
         'ceil': math.ceil, 'fact': math.factorial}
NAMES = {'pi': math.pi, 'e': math.e}
LIMIT = 200     # characters of the expression
BIG = 10 ** 300


def _num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError('not a number')
    if abs(x) > BIG:
        raise ValueError('too large')
    return x


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        return _num(node.value)
    if isinstance(node, ast.Name) and node.id in NAMES:
        return NAMES[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in UN:
        return UN[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in BIN:
        a, b = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(b) > 1000 or (abs(a) > 1 and abs(b) * math.log10(abs(a)) > 300)):
            raise ValueError('too large')
        return _num(BIN[type(node.op)](a, b))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS and not node.keywords:
        args = [_eval(a) for a in node.args]
        if node.func.id == 'fact' and (len(args) != 1 or args[0] > 500 or args[0] < 0 or args[0] != int(args[0])):
            raise ValueError('bad factorial')
        return _num(FUNCS[node.func.id](*(int(args[0]),) if node.func.id == 'fact' else args))
    raise ValueError('not allowed')


PERCENT = re.compile(r'(\d+(?:\.\d+)?)\s*%\s*(?:от|of|из)\s*', re.I)
TODAY = re.compile(r'(?i)\b(?:today|сегодня|сегодняшн\w+|오늘|今日|きょう)\b|(?<![\w])(?:오늘|今日|きょう)')
DATE = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')


def _clean(expr):
    s = str(expr or '').strip().replace('×', '*').replace('÷', '/').replace('−', '-').replace('^', '**')
    s = re.sub(r'(?<=\d),(?=\d)', '.', s)
    s = re.sub(r'(?<=\d)\s*[xхXХ]\s*(?=\d)', '*', s)
    s = PERCENT.sub(r'(\1/100)*', s)
    return re.sub(r'(\d)\s*%', r'(\1/100)', s)


def _shown(x):
    if isinstance(x, float):
        if x == int(x) and abs(x) < 1e15:
            return str(int(x))
        return '%.12g' % x
    return str(x)


def days(text):
    """'2026-01-01 - 2026-11-03' (two ISO dates) or 'YYYY-MM-DD + 90': how many days between, or the date after N days."""
    d = DATE.findall(text or '')
    try:
        if len(d) == 2:
            a, b = (datetime.date(*map(int, x)) for x in d)
            return '%d дн. между %s и %s' % (abs((b - a).days), a.isoformat(), b.isoformat())
        if len(d) == 1:
            m = re.search(r'([+-])\s*(\d{1,5})\s*(?:дн|д|d|day)?', DATE.sub('', text))
            if not m:     # a single date: which day of the week it is
                a = datetime.date(*map(int, d[0]))
                return '%s: %s' % (a.isoformat(), ('понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье')[a.weekday()])
            if m:
                a = datetime.date(*map(int, d[0]))
                r = a + datetime.timedelta(days=int(m.group(2)) * (1 if m.group(1) == '+' else -1))
                return '%s %s %s дн. = %s (%s)' % (a.isoformat(), m.group(1), m.group(2), r.isoformat(), ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')[r.weekday()])
    except (ValueError, OverflowError):
        return ''
    return ''


# ---- units: "10 km in miles", "5 фунтов в кг", "100°F в °C", "5キロをマイルに": a language model converts by feel, the program by factor ----
# name -> (dimension, size in the base unit of that dimension, aliases in ru / en / ko / ja); temperature is special-cased
_U = [
    ('mm', 'len', 0.001, 'мм миллиметр миллиметров миллиметра millimeter millimeters millimetre mm 밀리미터 ミリメートル ミリ'),
    ('cm', 'len', 0.01, 'см сантиметр сантиметров сантиметра centimeter centimeters centimetre cm 센티미터 센티 センチメートル センチ'),
    ('m', 'len', 1.0, 'м метр метров метра meter meters metre metres m 미터 メートル'),
    ('km', 'len', 1000.0, 'км километр километров километра kilometer kilometers kilometre kilometres km 킬로미터 킬로 キロメートル キロ'),
    ('in', 'len', 0.0254, 'дюйм дюймов дюйма inch inches 인치 インチ'),
    ('ft', 'len', 0.3048, 'фут футов фута foot feet ft 피트 フィート'),
    ('yd', 'len', 0.9144, 'ярд ярдов ярда yard yards yd 야드 ヤード'),
    ('mi', 'len', 1609.344, 'миля миль мили mile miles mi 마일 マイル'),
    ('g', 'mass', 0.001, 'г грамм граммов грамма gram grams g 그램 グラム'),
    ('kg', 'mass', 1.0, 'кг килограмм килограммов килограмма kilogram kilograms kg 킬로그램 キログラム'),
    ('t', 'mass', 1000.0, 'т тонна тонн тонны ton tons tonne tonnes 톤 トン'),
    ('lb', 'mass', 0.45359237, 'фунт фунтов фунта pound pounds lb lbs 파운드 ポンド'),
    ('oz', 'mass', 0.028349523125, 'унция унций унции ounce ounces oz 온스 オンス'),
    ('ml', 'vol', 0.001, 'мл миллилитр миллилитров миллилитра milliliter milliliters millilitre ml 밀리리터 ミリリットル'),
    ('l', 'vol', 1.0, 'л литр литров литра liter liters litre litres l 리터 リットル'),
    ('gal', 'vol', 3.785411784, 'галлон галлонов галлона gallon gallons gal 갤런 ガロン'),
    ('cup', 'vol', 0.2365882365, 'стакан стакана стаканов cup cups 컵 カップ'),
    ('mps', 'speed', 1.0, 'м/с m/s mps 미터매초 メートル毎秒'),
    ('kmh', 'speed', 1 / 3.6, 'км/ч km/h kph kmh 킬로미터매시 キロ毎時'),
    ('mph', 'speed', 0.44704, 'миль/ч mph mi/h 마일매시 マイル毎時'),
    ('b', 'data', 1.0, 'байт байта байтов byte bytes 바이트 バイト'),
    ('kb', 'data', 1024.0, 'кб килобайт килобайта килобайтов kb kilobyte kilobytes 킬로바이트 キロバイト'),
    ('mb', 'data', 1024.0 ** 2, 'мб мегабайт мегабайта мегабайтов mb megabyte megabytes 메가바이트 メガバイト'),
    ('gb', 'data', 1024.0 ** 3, 'гб гигабайт гигабайта гигабайтов gb gigabyte gigabytes 기가바이트 ギガバイト'),
    ('tb', 'data', 1024.0 ** 4, 'тб терабайт терабайта терабайтов tb terabyte terabytes 테라바이트 テラバイト'),
    ('s', 'time', 1.0, 'с сек секунда секунд секунды second seconds sec s 초 秒'),
    ('min', 'time', 60.0, 'мин минута минут минуты minute minutes min 분 分'),
    ('h', 'time', 3600.0, 'ч час часа часов hour hours hr h 시간 時間'),
    ('d', 'time', 86400.0, 'дн день дня дней day days 일 日'),
    ('wk', 'time', 604800.0, 'неделя недели недель week weeks 주 週間'),
    ('C', 'temp', 0, '°c c° цельсий цельсия градус градусов celsius 섭씨 摄氏 摂氏 度'),
    ('F', 'temp', 0, '°f f° фаренгейт фаренгейта fahrenheit 화씨 華氏'),
    ('K', 'temp', 0, 'к кельвин кельвина kelvin 켈빈 ケルビン'),
]
_ALIAS = {}
for _name, _dim, _size, _words in _U:
    for _w in _words.split():
        _ALIAS.setdefault(_w.lower(), (_name, _dim, _size))
_ALIAS.pop('c', None)   # a bare letter is only a unit with a degree sign or a number before it
_NUMBER = r'(-?\d+(?:[.,]\d+)?)'
_CONV = re.compile(r'^\s*' + _NUMBER + r'\s*°?\s*([^\W\d_/][\w/°]*|°\s*[cfkCFK])\s*(?:->|=>|→|=|to|in|into|в|на|во|を|は|으로|로|에서)\s*°?\s*([^\W\d_/][\w/°]*|°\s*[cfkCFK])\s*\w{0,6}\s*$', re.I)


def _unit(word):
    word = str(word).strip().lower().replace('°', '').replace(' ', '')
    if word in ('c', 'f', 'k'):
        return {'c': ('C', 'temp', 0), 'f': ('F', 'temp', 0), 'k': ('K', 'temp', 0)}[word]
    return _ALIAS.get(str(word).strip().lower().replace(' ', '')) or _ALIAS.get(word)


_CJK = re.compile(r'[぀-ヿ一-鿿가-힯]')
_SEP = re.compile(r'^\s*(?:->|=>|→|=|を|は|이|가|은|는|을|를|에서|から|to\b)?\s*')
_TAIL = re.compile(r'^\s*(?:に|へ|で|にして|にすると|だと|は|は？|으로|로|이야|예요|이에요|면|라면|는|은|입니까|ですか|いくつ|何|뭐야|얼마)?\s*(?:[?？.!。]*)\s*$')
_SHOWN = {'kmh': 'km/h', 'mps': 'm/s'}


def _split_cjk(rest):
    """'キロをマイルに' / '마일을 킬로미터로' -> (unit a, unit b) when the text is a unit, a particle, a unit and a closing particle."""
    words = sorted(_ALIAS, key=len, reverse=True)
    rest = rest.strip().lower()
    for a in words:
        if rest.startswith(a):
            after = _SEP.sub('', rest[len(a):], count=1)
            if after == rest[len(a):].strip() and not _CJK.match(after[:1] or 'x'):
                continue
            for b in words:
                if after.startswith(b) and _TAIL.match(after[len(b):]) and b != a:
                    return _ALIAS[a], _ALIAS[b]
    return None


def _answer(value, a, b):
    if a[1] != b[1] or a[0] == b[0]:
        return ''
    if a[1] == 'temp':
        kelvin = {'C': lambda v: v + 273.15, 'F': lambda v: (v - 32) * 5 / 9 + 273.15, 'K': lambda v: v}[a[0]](value)
        if kelvin < 0:
            return ''
        out = {'C': lambda k: k - 273.15, 'F': lambda k: (k - 273.15) * 9 / 5 + 32, 'K': lambda k: k}[b[0]](kelvin)
        sign = lambda u: ' K' if u == 'K' else '°' + u
        return '%s%s = %s%s' % (_shown(value), sign(a[0]), _shown(round(out, 6)), sign(b[0]))
    out = value * a[2] / b[2]
    return '%s %s = %s %s' % (_shown(value), _SHOWN.get(a[0], a[0]), _shown(float('%.9g' % out)), _SHOWN.get(b[0], b[0]))


def convert(text):
    """'10 km in miles' -> '10 km = 6.21371192 mi'; '' when it is not a conversion of two known units of one kind (money is not converted: rates change)."""
    raw = str(text or '').strip().rstrip('?.!？。')
    if not raw or len(raw) > 80:
        return ''
    m = _CONV.match(raw)
    if m:
        try:
            value = float(m.group(1).replace(',', '.'))
        except ValueError:
            return ''
        a, b = _unit(m.group(2)), _unit(m.group(3))
        if a and b:
            return _answer(value, a, b)
    n = re.match(r'^\s*' + _NUMBER + r'\s*(.+)$', raw)
    if n and _CJK.search(n.group(2)):
        pair = _split_cjk(n.group(2))
        if pair:
            try:
                return _answer(float(n.group(1).replace(',', '.')), *pair)
            except ValueError:
                return ''
    return ''


def calc(expr):
    """The exact value of an expression as text for her ('' when it is not a plain sum): 15% от 2300, 2**64, sqrt(2)*10, dates."""
    raw = str(expr or '').strip()
    if not raw or len(raw) > LIMIT:
        return ''
    raw = TODAY.sub(datetime.date.today().isoformat(), raw)    # "2027-01-01 - today": the program knows the date, she must not guess it
    if DATE.search(raw):
        return days(raw)
    unit = convert(raw)
    if unit:
        return unit
    try:
        value = _eval(ast.parse(_clean(raw), mode='eval'))
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError, RecursionError, MemoryError):
        return ''
    return '%s = %s' % (raw, _shown(value))
