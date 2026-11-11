"""Arithmetic said in words, done by the program: "сколько будет 17 умножить на 23", "посчитай 15% от 2300", "what is 17 times 23", "square root of 144", "17 곱하기 23은",
"17かける23は", "переведи 10 км в мили", "convert 100 F to C". A language model multiplies by feel and is often off by a digit, so when he asks in words (ru, en, ko, ja)
the program turns the sentence into an expression, counts it with exact.py and gives her the number in a bracketed note; she only says it. It needs a question or a
request word, so plain talk with numbers in it is left alone. Nothing here touches files or the network."""
import re

from luna.skills import exact

_ASK = re.compile(r'(?i)сколько|посчитай|подсчитай|вычисли|реши|чему\s+равн|что\s+получится|'
                  r'how\s+much\s+is|what\s+is|what.?s|calculate|compute|solve|evaluate|equals|'
                  r'계산|얼마|뭐야|몇\s*이야|(?:은|는)\s*[?？]|'
                  r'いくつ|計算|何になる|(?:は|って)\s*[?？]|=\s*[?？]?\s*$')
_CONVERT = re.compile(r'(?i)^\s*(?:пожалуйста,?\s*)?(?:переведи|конвертируй|сколько\s+будет|сколько\s+это|convert|what\s+is|how\s+much\s+is|how\s+many\s+is)\s+(?P<rest>.+?)\s*(?:пожалуйста|please|[?!.？])?\s*$')
_CONVERT_AFTER = re.compile(r'(?i)^\s*(?P<rest>.+?)\s+(?:пожалуйста\s+)?(?:переведи|конвертируй|please convert|convert it)\s*[?!.？]*\s*$')
_NUM = r'(\d+(?:[.,]\d+)?)'
_STEPS = [
    (re.compile(_NUM + r'\s*(?:%|процент\w*|percent|per\s*cent|퍼센트|パーセント)\s*(?:от|of)\s*' + _NUM, re.I), r'(\2*\1/100)'),
    (re.compile(_NUM + r'\s*(?:의|の)\s*' + _NUM + r'\s*(?:%|퍼센트|パーセント)'), r'(\1*\2/100)'),
    (re.compile(r'(?:квадратный\s+)?корень\s+(?:квадратный\s+)?из\s*' + _NUM, re.I), r'sqrt(\1)'),
    (re.compile(r'square\s+root\s+of\s*' + _NUM, re.I), r'sqrt(\1)'),
    (re.compile(_NUM + r'\s*(?:의\s*제곱근|の平方根|の√)'), r'sqrt(\1)'),
    (re.compile(r'(?:в\s+степени|to\s+the\s+power\s+of|raised\s+to|\^)', re.I), '**'),
    (re.compile(r'(?:умножить\s+на|помножить\s+на|умножь\s+на|multiplied\s+by|\btimes\b|곱하기|かける|掛ける|×|(?<=\d)\s*[xхXХ]\s*(?=\d))', re.I), '*'),
    (re.compile(r'(?:разделить\s+на|поделить\s+на|делить\s+на|divided\s+by|\bover\b|나누기|割る|わる|÷)', re.I), '/'),
    (re.compile(r'(?:\bплюс\b|\bplus\b|더하기|足す|たす)', re.I), '+'),
    (re.compile(r'(?:\bминус\b|\bminus\b|빼기|引く|ひく)', re.I), '-'),
    (re.compile(r'(\d),(\d{1,2})(?!\d)'), r'\1.\2'),
]
_TERM = r'(?:\d+(?:\.\d+)?|sqrt\(\d+(?:\.\d+)?\)|\([^()]*\))'
_EXPR = re.compile(r'(?:%s|\(%s\))(?:\s*(?:\*\*|[-+*/])\s*%s)+|sqrt\(\d+(?:\.\d+)?\)' % (_TERM, _TERM, _TERM))


def expression(text):
    """The arithmetic expression hidden in the sentence, or '' (no question word, a date, or nothing to count)."""
    text = ' '.join(str(text or '').split())[:200]
    if not text or exact.DATE.search(text):
        return ''
    asked = bool(_ASK.search(text))
    for rx, repl in _STEPS:
        text = rx.sub(repl, text)
    best = ''
    for m in _EXPR.finditer(text):
        if len(m.group(0)) > len(best):
            best = m.group(0)
    if best and not asked:     # no question word: only a sentence that is almost nothing but the sum ("square root of 144", "17 x 23")
        asked = len(best) >= 0.6 * len(re.sub(r'[\s?!.=？]+', '', text)) and len(text) <= 40
    return best.strip() if asked else ''


def answer(text):
    """('calc' | 'convert', result) or None."""
    raw = ' '.join(str(text or '').split())[:200]
    m = _CONVERT.match(raw) or _CONVERT_AFTER.match(raw)
    if m:
        res = exact.convert(m.group('rest'))
        if res:
            return 'convert', res
    expr = expression(raw)
    if expr:
        res = exact.calc(expr)
        if res and '=' in res:
            return 'calc', res
    return None


def hint(text):
    got = answer(text)
    if not got:
        return ''
    return ('[Программа посчитала точно: %s. Назови именно это число, не пересчитывай и не округляй по-своему; если он просит объяснить ход, покажи его коротко.]' % got[1])
