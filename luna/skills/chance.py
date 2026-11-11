"""Chance, done by the program and not by feel: a coin, dice ("2d6", "d20"), a random number in a range, and "pick one of these". A language model that is asked
for "a random number" tends to say 7 or 42, so when he asks in words (ru, en, ko, ja) the program throws and tells her the result; she only announces it in her own way.
Nothing here touches files or the network."""
import random
import re

RNG = random.SystemRandom()
MAX_DICE = 20
MAX_SIDES = 1000
MAX_OPTIONS = 12

_COIN = re.compile(r'(?i)подбрось монет\w*|кинь монет\w*|брось монет\w*|орёл или решка|орел или решка|flip a coin|toss a coin|coin ?flip|heads or tails|동전 ?(?:던져|돌려|튕겨)|앞면 ?(?:이야|이냐|아니면)|コイン(?:を)?(?:投げて|トス)|コイントス|表か裏')
_DICE = [
    re.compile(r'(?i)(?:брось|кинь|подбрось|бросай)\s+(?:кубик\w*|кост\w+)\s*(?:(?P<n>\d{1,2})?\s*[dд]\s*(?P<s>\d{1,4}))?'),
    re.compile(r'(?i)(?:брось|кинь|бросай)\s+(?P<n>\d{1,2})?\s*[dд]\s*(?P<s>\d{1,4})\b'),
    re.compile(r'(?i)\broll\s+(?:an?\s+|the\s+)?(?:(?P<n>\d{1,2})?\s*d\s*(?P<s>\d{1,4})|dice|die)'),
    re.compile(r'(?i)주사위\s*(?:를\s*)?(?:굴려|던져)|(?:(?P<n>\d{1,2})?\s*d\s*(?P<s>\d{1,4}))\s*(?:굴려|던져)'),
    re.compile(r'(?i)サイコロ\s*(?:を\s*)?(?:振って|ふって|投げて)|(?P<n>\d{1,2})?\s*d\s*(?P<s>\d{1,4})\s*(?:を)?\s*振って'),
]
_RANGE = [
    re.compile(r'(?i)случайн\w+ числ\w+\s*(?:от|между)?\s*(?P<a>-?\d+)\s*(?:до|и|-|–)\s*(?P<b>-?\d+)'),
    re.compile(r'(?i)random number\s*(?:between|from)?\s*(?P<a>-?\d+)\s*(?:and|to|-|–)\s*(?P<b>-?\d+)'),
    re.compile(r'(?P<a>-?\d+)\s*(?:부터|에서|~|-)\s*(?P<b>-?\d+)\s*(?:까지|사이)?\s*(?:중에?\s*|의\s*)?(?:랜덤|무작위|아무)'),
    re.compile(r'(?P<a>-?\d+)\s*(?:から|〜|~|-)\s*(?P<b>-?\d+)\s*(?:の間|まで)?\s*(?:で|の)?\s*(?:ランダム|乱数|適当な数)'),
]
_PICK = [
    re.compile(r'(?is)\b(?:выбери|реши|определись|подскажи)\b[^:\n]{0,20}?[:\-—]?\s*(?P<opts>[^?!.]+?\s(?:или|либо)\s[^?!.]+)'),
    re.compile(r'(?is)\b(?:choose|pick|decide|choose between|pick between)\b\s*(?:between|one of|from)?\s*[:\-—]?\s*(?P<opts>[^?!.]+?(?:\bor\b|,)[^?!.]+)'),
    re.compile(r'(?is)(?P<opts>[^?!.]+?(?:아니면|이랑|랑|,)[^?!.]+?)\s*중에?\s*(?:하나\s*)?(?:골라|뽑아|정해)'),
    re.compile(r'(?is)(?P<opts>[^?!。]+?(?:か|、|,)[^?!。]+?)\s*(?:の中)?から?\s*(?:どれか\s*)?(?:選んで|決めて|えらんで)'),
]
_SPLIT = re.compile(r'\s*(?:,|;|、|，|/|\bor\b|\bили\b|\bлибо\b|아니면|か(?=[^\s])|\n)\s*', re.I)


def _options(raw):
    out, seen = [], set()
    for part in _SPLIT.split(str(raw or '')):
        part = part.strip(' "«»\'').strip()
        part = re.sub(r'(?i)^(?:между|between|one of|из)\s+', '', part)
        part = re.sub(r'(?i)^(?:лучше|что|what to)\s+', '', part)
        part = re.sub(r'(?i)^(?:one|один|одно)\s*:\s*', '', part)
        part = re.sub(r'(?i)\s+(?:пожалуйста|please)$', '', part).strip()
        if part and part.lower() not in seen and len(part) <= 60:
            seen.add(part.lower())
            out.append(part)
    return out[:MAX_OPTIONS]


def parse(text):
    """('coin',) | ('dice', n, sides) | ('range', a, b) | ('pick', [options]) or None. Plain talk about coins or dice is not a request."""
    text = ' '.join(str(text or '').split())[:300]
    if not text:
        return None
    if _COIN.search(text):
        return ('coin',)
    for rx in _DICE:
        m = rx.search(text)
        if m:
            g = m.groupdict()
            n, sides = int(g.get('n') or 1), int(g.get('s') or 6)
            return ('dice', max(1, min(n, MAX_DICE)), max(2, min(sides, MAX_SIDES)))
    for rx in _RANGE:
        m = rx.search(text)
        if m:
            a, b = int(m.group('a')), int(m.group('b'))
            if abs(a) < 10 ** 12 and abs(b) < 10 ** 12:
                return ('range', min(a, b), max(a, b))
    for rx in _PICK:
        m = rx.search(text)
        if m:
            opts = _options(m.group('opts'))
            if len(opts) >= 2:
                return ('pick', opts)
    return None


def throw(request):
    """The result as a sentence of fact for her."""
    kind = request[0]
    if kind == 'coin':
        return 'монета: ' + RNG.choice(['орёл', 'решка'])
    if kind == 'dice':
        _, n, sides = request
        rolls = [RNG.randint(1, sides) for _ in range(n)]
        return 'кубик %dd%d: %s%s' % (n, sides, ', '.join(map(str, rolls)), ' (сумма %d)' % sum(rolls) if n > 1 else '')
    if kind == 'range':
        return 'случайное число от %d до %d: %d' % (request[1], request[2], RNG.randint(request[1], request[2]))
    return 'выбор из вариантов (%s): %s' % ('; '.join(request[1]), RNG.choice(request[1]))


def hint(text):
    """The note for her with the real result, or '' when he did not ask for a throw."""
    req = parse(text)
    if not req:
        return ''
    return ('[Программа бросила жребий по его просьбе: %s. Назови ему именно этот результат, не меняй его и не бросай «в уме»; отреагируй по-своему, '
            'коротко (можно с юмором, это жребий, а не приказ).]' % throw(req))
