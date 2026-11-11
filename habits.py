"""Habits she keeps for him: "заведи привычку зарядка", "отметь зарядку", "как мои привычки", "track a habit: reading", "mark reading as done", "습관 추가 운동",
"운동 체크해줘", "習慣を追加 読書", "読書を記録して". The program counts days and streaks (a language model cannot count days reliably) and tells her the real
numbers in a bracketed note; she only retells it, warmly. A broken streak is never a reproach: the note tells her to support him, not to scold.
Everything stays in habits.json next to the program (nothing is sent anywhere). One habit can be dropped at his word; there is no "wipe everything".
In ru, en, ko and ja."""
import paths
import json
import os
import re
import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

MAX_HABITS = 10
MAX_NAME = 40
KEEP_DAYS = 800        # days kept per habit
MILESTONES = (3, 7, 14, 21, 30, 50, 100, 200, 365)


def _file():
    return paths.data_file('habits.json')


FILE = _file()
_lock = threading.RLock()

_WORD = re.compile(r'(?i)привыч|habit|습관|習慣')
_YEST = re.compile(r'(?i)\bвчера\b|\byesterday\b|어제|昨日|きのう')

_START = [
    re.compile(r'(?is)\b(?:заведи|добавь|начни отслеживать|давай отслеживать|отслеживай|веди|создай)\s+(?:мне\s+|мою\s+|новую\s+)*привычк\w*\s*[:\-—]?\s*(?P<name>.+)'),
    re.compile(r'(?is)\b(?:track|start tracking|add|new|create)\s+(?:a\s+|the\s+|my\s+|new\s+)*habit\s*[:\-—]?\s*(?P<name>.+)'),
    re.compile(r'(?is)\b(?:track|start tracking)\s+my\s+(?P<name>.+?)\s+habit\b'),
    re.compile(r'(?is)(?P<name>[^\n]+?)\s*습관\s*(?:을|를)?\s*(?:추가|등록|만들어|시작)'),
    re.compile(r'(?is)습관\s*(?:추가|등록)\s*[:\-]?\s*(?P<name>.+)'),
    re.compile(r'(?is)(?P<name>[^\n]+?)\s*を?\s*習慣に\s*(?:して|追加|登録)'),
    re.compile(r'(?is)習慣\s*(?:を)?\s*(?:追加|登録)\s*[:：]?\s*(?P<name>.+)'),
    re.compile(r'(?is)(?P<name>[^\n]+?)\s*の習慣を\s*(?:追加|登録|始め)'),
]
_DROP = [
    re.compile(r'(?is)\b(?:удали|убери|перестань отслеживать|хватит отслеживать)\s+привычк\w*\s*[:\-—]?\s*(?P<name>.+)'),
    re.compile(r'(?is)\b(?:remove|delete|stop tracking|drop)\s+(?:the\s+|my\s+)?(?P<name>.+?)\s+habit\b'),
    re.compile(r'(?is)\b(?:remove|delete|stop tracking|drop)\s+(?:the\s+|my\s+)?habit\s*[:\-—]?\s*(?P<name>.+)'),
    re.compile(r'(?is)(?P<name>[^\n]+?)\s*습관\s*(?:을|를)?\s*(?:삭제|지워|제거|그만)'),
    re.compile(r'(?is)(?P<name>[^\n]+?)\s*の?\s*習慣を?\s*(?:削除|消して|やめ)'),
]
_MARK = [
    re.compile(r'(?is)\b(?:отметь|засчитай|зачти|отмечай|отметить)\s+(?:мне\s+|сегодня\s+|вчера\s+|привычку\s+)*(?P<name>.+)'),
    re.compile(r'(?is)\b(?:mark|check off|tick off|count|log)\s+(?:my\s+|the\s+|today.s\s+)?(?P<name>.+?)\s+(?:habit\s+)?(?:as\s+)?(?:done|complete\w*|finished)\b'),
    re.compile(r'(?is)\b(?:mark|check off|tick off|count|log)\s+(?:my\s+|the\s+)?(?P<name>.+?)\s+habit\b'),
    re.compile(r'(?is)(?P<name>[^\n]+?)\s*(?:을|를)?\s*(?:체크|완료\s*처리|기록)\s*(?:해줘|해 줘|해주세요|해요|해)'),
    re.compile(r'(?is)(?P<name>[^\n]+?)\s*(?:했어|했다|했음).{0,8}(?:체크|기록)'),
    re.compile(r'(?is)(?P<name>[^\n]+?)\s*を?\s*(?:チェック|記録|済みに)\s*(?:して|してね|しといて|しておいて)'),
    re.compile(r'(?is)(?P<name>[^\n]+?)\s*(?:した|やった|できた).{0,8}(?:記録|チェック)'),
]
_SHOW = re.compile(r'(?i)(?:как|что|покажи|расскажи|скажи|сколько)\s+(?:там\s+)?(?:(?:у\s+)?(?:мо\w+|наш\w+)\s+)?привыч|как дела с привыч|что с (?:мо\w+\s+)?привыч|мои привычки|привычки как|'
                   r'(?:show|how are|how.s|what are|tell me about)\s+(?:my\s+)?habits?|habit\w*\s+(?:streak|progress|status)|my habits|'
                   r'습관.{0,10}(?:현황|상황|어때|보여|알려|연속|진행)|'
                   r'習慣.{0,10}(?:状況|どう|見せて|教えて|連続|進み)')

_TRAIL = re.compile(r'(?i)(?:\s*(?:сегодня|вчера|выполнен\w*|сделан\w*|готов\w*|пожалуйста|please|today|yesterday|for today|as done|done|오늘|어제|今日|昨日)\b)+\s*$')


def _clean(name):
    name = str(name or '').strip()
    name = re.sub(r'[.!?。！？]+\s*$', '', name).strip()
    name = _TRAIL.sub('', name).strip(' "«»\'.,')
    name = re.sub(r'(?i)^(?:мне|мою|свою|мой|my|the|a|an|new|новую)\s+', '', name).strip()
    name = re.sub(r'(?i)\s+(?:привычк\w*|habit)$', '', name).strip()
    if re.search(r'[가-힣぀-ヿ一-鿿]', name):
        name = re.sub(r'(?:을|를|은|는|도|を|は|も)$', '', name).strip()
    return name[:MAX_NAME]


def _stem(name):
    name = str(name).lower().strip()
    name = re.sub(r'\s+', ' ', name)
    return name[:-1] if len(name) > 3 and re.search(r'[а-яёa-z]$', name) else name


def _same(a, b):
    x, y = _stem(a), _stem(b)
    return bool(x and y and (x == y or (len(min(x, y, key=len)) >= 3 and (x in y or y in x))))


def load():
    with _lock:
        try:
            data = json.loads(FILE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
    out = {}
    raw = data.get('habits') if isinstance(data, dict) else None
    if isinstance(raw, dict):
        for name, info in list(raw.items())[:MAX_HABITS]:
            days = info.get('days') if isinstance(info, dict) else None
            good = []
            for d in days if isinstance(days, list) else []:
                try:
                    date.fromisoformat(str(d))
                    good.append(str(d))
                except ValueError:
                    pass
            out[str(name)[:MAX_NAME]] = {'days': sorted(set(good))[-KEEP_DAYS:]}
    return out


def _save(habits):
    with _lock:
        try:
            tmp = FILE.with_suffix('.tmp')
            tmp.write_text(json.dumps({'habits': habits}, ensure_ascii=False, indent=1), encoding='utf-8')
            os.replace(tmp, FILE)
            return True
        except OSError:
            return False


def streaks(days, today):
    """(current streak, best streak, total) from ISO day strings. The current streak survives until the end of today: if today is not marked yet it counts from yesterday."""
    ds = sorted({date.fromisoformat(d) for d in days})
    if not ds:
        return 0, 0, 0
    best = run = 1
    for a, b in zip(ds, ds[1:]):
        run = run + 1 if (b - a).days == 1 else 1
        best = max(best, run)
    have = set(ds)
    cur, d = 0, today if today in have else today - timedelta(days=1)
    while d in have:
        cur += 1
        d -= timedelta(days=1)
    return cur, best, len(ds)


def _find(habits, name):
    for known in habits:
        if _same(known, name):
            return known
    return None


def parse(text):
    """('start'|'drop'|'mark'|'show', name, day offset) or None. Plain talk about habits is not a request."""
    text = ' '.join(str(text or '').split())[:300]
    if not text:
        return None
    offset = -1 if _YEST.search(text) else 0
    if _SHOW.search(text):
        return ('show', '', 0)
    for rx in _DROP:
        m = rx.search(text)
        if m and _clean(m.group('name')):
            return ('drop', _clean(m.group('name')), 0)
    for rx in _START:
        m = rx.search(text)
        if m and _clean(m.group('name')):
            return ('start', _clean(m.group('name')), 0)
    for rx in _MARK:
        m = rx.search(text)
        if m and _clean(m.group('name')):
            return ('mark', _clean(m.group('name')), offset)
    return None


def _line(name, info, today):
    cur, best, total = streaks(info['days'], today)
    done = today.isoformat() in info['days']
    return '%s: серия %d дн.%s, лучшая %d, всего %d' % (name, cur, ' (сегодня уже отмечено)' if done else ' (сегодня ещё нет)', best, total)


def pending(today=None):
    """Names of his habits not yet marked today (for "what is on today")."""
    today = (today or date.today()).isoformat()
    return [n for n, i in load().items() if today not in i['days']]


def handle(text, today=None):
    """The note for her with what the program did, or '' when he did not ask about habits. `today` is injected by the tests."""
    req = parse(text)
    if not req:
        return ''
    kind, name, offset = req
    today = today or date.today()
    habits = load()
    if kind == 'show':
        if not habits:
            return '[Привычек пока нет: он их ещё не заводил. Скажи, что можно сказать «заведи привычку …», и всё; не выдумывай привычки.]'
        lines = '; '.join(_line(n, i, today) for n, i in habits.items())
        return ('[Его привычки, посчитала программа: %s. Назови именно эти числа, не пересчитывай. Если серия прервалась, не упрекай, а поддержи и скажи, что можно начать снова '
                'с сегодняшнего дня; если серия круглая или рекордная, порадуйся по-своему, коротко.]' % lines)
    if kind == 'start':
        known = _find(habits, name)
        if known:
            return '[Привычка «%s» уже есть: %s. Скажи ему об этом, ничего не дублируй.]' % (known, _line(known, habits[known], today))
        if len(habits) >= MAX_HABITS:
            return '[Привычек уже %d, больше программа не ведёт. Скажи честно и предложи убрать одну: «удали привычку …».]' % MAX_HABITS
        habits[name] = {'days': []}
        if not _save(habits):
            return '[Привычку «%s» записать не удалось: файл недоступен. Скажи честно, что не записалась.]' % name
        return '[Программа завела привычку «%s»: счёт начнётся с первой отметки. Тепло подтверди, без нотаций; он отмечает её словами «отметь %s».]' % (name, name)
    if kind == 'drop':
        known = _find(habits, name)
        if not known:
            return '[Привычки «%s» нет среди его привычек (есть: %s). Скажи честно, что такой не нашла.]' % (name, ', '.join(habits) or 'пока ни одной')
        del habits[known]
        _save(habits)
        return '[Программа убрала привычку «%s» по его слову. Подтверди спокойно, без сожалений и нотаций.]' % known
    # mark
    known = _find(habits, name)
    if not known:
        if _WORD.search(str(text)):
            return ('[Привычки «%s» среди его привычек нет (есть: %s). Скажи честно и предложи завести: «заведи привычку …». Ничего не отмечено.]' % (name, ', '.join(habits) or 'пока ни одной'))
        return ''    # "отметь это" / "記録して" about something else: not ours
    day = today + timedelta(days=offset)
    iso = day.isoformat()
    info = habits[known]
    if iso in info['days']:
        return '[«%s» за %s уже была отмечена; второй раз не считается. Скажи ему мягко: %s.]' % (known, 'вчера' if offset else 'сегодня', _line(known, info, today))
    info['days'] = sorted(set(info['days'] + [iso]))[-KEEP_DAYS:]
    if not _save(habits):
        return '[Отметить «%s» не удалось: файл недоступен. Скажи честно, что не записалось.]' % known
    cur, best, total = streaks(info['days'], today)
    extra = ''
    if cur in MILESTONES:
        extra = ' Это круглая серия (%d), порадуйся по-своему.' % cur
    elif cur == best and cur > 3:
        extra = ' Это его лучшая серия, отметь это.'
    return ('[Программа отметила «%s» за %s. Теперь: серия %d дн., лучшая %d, всего %d.%s Назови именно эти числа, не пересчитывай; коротко и тепло.]'
            % (known, 'вчера' if offset else 'сегодня', cur, best, total, extra))
