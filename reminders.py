"""A reminder he asks for in a message ("remind me in 10 minutes about tea"): the program reads the time and the subject, keeps it, and when it is due
she speaks first. Only relative times ("in 10 minutes", "in 2 hours") and a clock time ("at 18:30") are understood; anything else she says honestly that she
could not set. In ru, en, ko and ja. Nothing is run or changed outside her own memory."""
import re
import time

import lexicon

MAX_SUBJECT = 80
MAX_AHEAD = 24 * 3600          # a time without a day: within the next day
MAX_DAYS = 3 * 24 * 3600      # with "tomorrow" / "the day after": within three days

_NUM = {'пол': 0.5, 'half': 0.5, 'an': 1, 'a': 1, 'one': 1, 'час': 1, 'минуту': 1}

# a relative time: (number or word) + unit, per language
_REL = [
    re.compile(r'(?i)через\s+(?P<n>\d+|пол\s?часа|полчаса|час|минуту|полтора часа)\s*(?P<u>минут\w*|мин\b|час\w*|ч\b)?'),
    re.compile(r'(?i)\bin\s+(?P<n>\d+|an|a|half an|one)\s*(?P<u>minutes?|mins?|hours?|hrs?)'),
    re.compile(r'(?P<n>\d+)\s*(?P<u>시간)(?=\s*(?:\d+\s*분|반)\s*(?:뒤|후))'),   # "1시간 30분 뒤": the hours first, the minutes are added below
    re.compile(r'(?P<n>\d+)\s*(?P<u>時間)(?=\s*(?:\d+\s*分|半)\s*後)'),
    re.compile(r'(?P<n>\d+)\s*(?P<u>분|시간)\s*(?:뒤|후)'),
    re.compile(r'(?P<n>\d+)\s*(?P<u>分|時間)\s*後'),
]

def _seconds(n, unit):
    n = str(n).lower().replace(' ', '')
    unit = (unit or '').lower()
    if n in ('полчаса', 'пол' + 'часа', 'halfan'):
        return 1800
    if n == 'полтора' + 'часа':
        return 5400
    if n in ('час', 'an', 'a', 'one'):
        value = 1
        unit = unit or 'час'
    elif n == 'минуту':
        value, unit = 1, 'мин'
    else:
        value = int(n)
    hours = unit.startswith(('час', 'ч', 'hour', 'hr')) or unit in ('시간', '時間')
    return value * (3600 if hours else 60)


# what follows an hour count: "1 hour 30 minutes", "полтора часа" is handled above; "и 20 минут", "and a half", "1시간 반", "1時間半"
_MORE_MIN = re.compile(r'(?i)^\s*(?:и\s*|and\s*)?(?P<n>\d+)\s*(?:минут\w*|мин\b|minutes?|mins?|분|分)(?:\s*(?:뒤|후|後))?')
_MORE_HALF = re.compile(r'(?i)^\s*(?:и\s*пол\w*|and a half|반|半)(?:\s*(?:뒤|후|後))?')

# a clock time: "18:30", "в 6 вечера", "at 6pm", "오후 6시 반", "午後6時半", "18時に"
_CLOCK = re.compile(r'(?i)(?:\bв|\bat|\bна)?\s*(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)\b\s*(?P<ap>[ap]\.?m\.?\b)?')
_CLOCK_RU = re.compile(r'(?i)\b(?:в|на)\s+(?P<h>\d{1,2})(?:[:.](?P<m>[0-5]\d))?\s*(?:час\w*\s*)?(?P<dp>утра|дня|вечера|ночи)\b')
_CLOCK_RU_H = re.compile(r'(?i)\b(?:в|на)\s+(?P<h>\d{1,2})\s*(?:часов|часа|час)\b(?!\s*(?:через|назад))')
_CLOCK_EN = re.compile(r'(?i)\b(?:at\s+)?(?P<h>\d{1,2})(?::(?P<m>[0-5]\d))?\s*(?P<ap>[ap]\.?m\.?)(?![a-z])')
_CLOCK_EN_AT = re.compile(r'(?i)\bat\s+(?P<h>\d{1,2})\b(?!\s*(?:%|minutes?|mins?|hours?|:|\d))')
_CLOCK_KO = re.compile(r'(?P<dp>오전|오후|아침|저녁|밤|새벽)?\s*(?P<h>\d{1,2})\s*시(?!간)\s*(?:(?P<m>\d{1,2})\s*분|(?P<half>반))?')
_CLOCK_JA = re.compile(r'(?P<dp>午前|午後|朝|夜|夕方|夕|晩)?\s*(?P<h>\d{1,2})\s*時(?!間)\s*(?:(?P<m>\d{1,2})\s*分|(?P<half>半))?')
_DAY = [(re.compile(r'(?i)\bпослезавтра\b|\bday after tomorrow\b|모레|明後日|あさって'), 2),
        (re.compile(r'(?i)\bзавтра\b|\btomorrow\b|내일|明日|あした|あす'), 1)]
# words that only describe the time of day: they leave the subject once the time is read
_DAYPART = re.compile(r'(?i)\b(?:утром|вечером|днём|днем|ночью|утра|вечера|дня|ночи)\b|오전|오후|아침|저녁|내일|모레|午前|午後|明後日|明日|あした|あさって|\b(?:tomorrow|morning|evening|tonight)\b|завтра|послезавтра')
_PM = {'вечера': 'pm', 'дня': 'pm', 'утра': 'am', 'ночи': 'night', '오후': 'pm', '저녁': 'pm', '밤': 'pm', '오전': 'am', '아침': 'am', '새벽': 'am',
       '午後': 'pm', '夕方': 'pm', '夕': 'pm', '晩': 'pm', '夜': 'pm', '午前': 'am', '朝': 'am'}


def _hour(h, part):
    """The 24-hour hour from a 12-hour reading and a part of the day ('am' / 'pm' / 'night'); None for an impossible hour."""
    part = str(part or '').lower().replace('.', '')
    part = _PM.get(part, part)
    if h > 24 or (part and h > 12):
        return None
    if part == 'pm':
        return h + 12 if h < 12 else h
    if part == 'am':
        return 0 if h == 12 else h
    if part == 'night':
        return 0 if h == 12 else h if h < 6 else h + 12 if h < 12 else h
    return h % 24


def _clock_time(text):
    """(hour, minute, span) of a clock time in the text, or None."""
    for rx in (_CLOCK_RU, _CLOCK_RU_H, _CLOCK_EN, _CLOCK, _CLOCK_EN_AT, _CLOCK_KO, _CLOCK_JA):
        for m in rx.finditer(text):
            g = m.groupdict()
            minute = 30 if g.get('half') else int(g.get('m') or 0)
            hour = _hour(int(g['h']), g.get('dp') or g.get('ap'))
            if hour is not None and minute < 60:
                return hour, minute, m.span()
    return None


def _day_shift(text):
    for rx, days in _DAY:
        m = rx.search(text)
        if m:
            return days
    return 0


def wants(text):
    return bool(lexicon.rx('remind').search(str(text or '')))


def parse(text, now=None):
    """(due time, what about) or None. None also when he asked but gave a time the program does not understand."""
    text = str(text or '')
    if not wants(text):
        return None
    now = now or time.time()
    due, cut = None, None
    for rx in _REL:
        m = rx.search(text)
        if m:
            try:
                seconds = _seconds(m.group('n'), m.group('u'))
            except (ValueError, TypeError):
                continue
            end = m.end()
            if seconds % 3600 == 0 and seconds:     # "1 hour 30 minutes", "1 hour and a half"
                more = _MORE_MIN.match(text[end:])
                half = _MORE_HALF.match(text[end:])
                if more:
                    seconds, end = seconds + int(more.group('n')) * 60, end + more.end()
                elif half:
                    seconds, end = seconds + 1800, end + half.end()
            due, cut = now + seconds, (m.start(), end)
            break
    limit = MAX_AHEAD
    if due is None:
        found = _clock_time(text)
        if found:
            hour, minute, cut = found
            local = time.localtime(now)
            days = _day_shift(text)
            target = time.mktime((local.tm_year, local.tm_mon, local.tm_mday + days, hour, minute, 0, 0, 0, -1))
            if target <= now and not days:
                target += 86400       # "at 7" said at 9 p.m. is tomorrow's 7
            due, limit = target, MAX_DAYS if days else MAX_AHEAD
    if due is None or not 30 <= due - now <= limit:
        return None
    rest = (text[:cut[0]] + ' ' + text[cut[1]:])
    rest = re.sub(r'알려\s*줘요?|알려\s*주세요|알려\s*줄래|말해\s*줘요?|깨워\s*줘요?|알람\s*맞춰\s*줘요?|맞춰\s*줘요?|教えて(?:ください|くれ)?|知らせて(?:ください)?|起こして(?:ください)?|して(?:ください)?$', ' ', rest)
    rest = _DAYPART.sub(' ', rest)
    rest = lexicon.rx('remind').sub(' ', rest)
    rest = _DAYPART.sub(' ', rest)
    rest = re.sub(r'(?i)\b(мне|пожалуйста|про|о|об|что|me|please|to|about|that)\b|[,.!?]|[에을를에게]\s*$', ' ', rest)
    rest = re.sub(r'^\s*(?:에는|에|には|に|の)\s*|\s+(?:에|に)\s*$', ' ', rest)
    return due, ' '.join(rest.split())[:MAX_SUBJECT]


def clock(due):
    return time.strftime('%H:%M', time.localtime(due))


# ---- seeing and cancelling what she keeps: "what reminders do I have", "cancel the reminder about tea" (ru, en, ko, ja) ----
_LIST_RQ = [
    re.compile(r'(?i)\b(?:какие|что|покажи|назови|скажи|прочитай|есть ли).{0,24}напоминани\w*|мои напоминания|напоминани\w* (?:на сегодня|есть)'),
    re.compile(r'(?i)(?:what|which|show|list|read|any|do i have).{0,24}\breminders?\b|\bmy reminders\b'),
    re.compile(r'(?:알림|리마인더|알람).{0,12}(?:뭐|보여|알려|목록|있어|뭔지)'),
    re.compile(r'(?:リマインダー|アラーム|通知).{0,8}(?:見せて|教えて|何|ある)'),
]
_CANCEL_RQ = [
    re.compile(r'(?is)\b(?:отмени|удали|убери|сними|забудь|сотри)\s+(?:моё\s+|мое\s+|мои\s+)?(?P<all>все\s+|всё\s+)?напоминани\w*\s*(?:про|о|об|на)?\s*(?P<what>.*)'),
    re.compile(r'(?is)\b(?:cancel|delete|remove|clear|forget)\s+(?:my\s+|the\s+|that\s+)?(?P<all>all\s+(?:my\s+|the\s+)?)?(?:reminders?|alarms?)\s*(?:about|for|to|of)?\s*(?P<what>.*)'),
    re.compile(r'(?s)(?P<what>.*?)\s*(?P<all>전부\s*|모든\s*)?(?:알림|알람|리마인더)\s*(?:을|를)?\s*(?:취소|삭제|지워|없애)'),
    re.compile(r'(?s)(?P<what>.*?)の?\s*(?P<all>全部の?|すべての)?(?:リマインダー|アラーム|通知)\s*を?\s*(?:キャンセル|消して|削除|取り消して|やめて)'),
]


def manage_kind(text):
    """'list' or 'cancel' when he asks to see or cancel his reminders, else ''."""
    text = str(text or '')[:300]
    if any(rx.search(text) for rx in _CANCEL_RQ):
        return 'cancel'
    if any(rx.search(text) for rx in _LIST_RQ):
        return 'list'
    return ''


def _when(due):
    local, now = time.localtime(due), time.localtime()
    day = '' if (local.tm_year, local.tm_yday) == (now.tm_year, now.tm_yday) else time.strftime('%d.%m ', local)
    return day + time.strftime('%H:%M', local)


def manage(text, items):
    """Do it on the list `items` (her memory's reminders, changed in place) and return the hint for her, or '' when the message is not about that."""
    kind = manage_kind(text)
    if not kind:
        return ''
    if kind == 'list':
        if not items:
            return '[Он спросил про напоминания: сейчас у него их нет. Скажи это коротко.]'
        return '[Его напоминания, которые ты хранишь: %s. Перечисли их как есть, коротко.]' % '; '.join('%s%s' % (_when(e['due']), ' — ' + e['text'] if e.get('text') else '') for e in items)
    what, every = '', False
    for rx in _CANCEL_RQ:
        m = rx.search(str(text)[:300])
        if m:
            what, every = (m.group('what') or '').strip(' ,.!?。！？"«»'), bool(m.group('all'))
            break
    if not items:
        return '[Он просит отменить напоминание, но их нет. Скажи это.]'
    if every:
        gone = list(items)
    elif what:
        words = [w for w in re.split(r'\s+', what.lower()) if len(w) >= 3]
        gone = [e for e in items if any(w[:5] in e.get('text', '').lower() for w in words)] if words else []
    else:
        gone = list(items) if len(items) == 1 else []
    if not gone:
        return ('[Он просит отменить напоминание, но программа не поняла какое. Сейчас есть: %s. Спроси, какое именно убрать.]'
                % '; '.join(e.get('text') or _when(e['due']) for e in items))
    for e in gone:
        items.remove(e)
    return '[Программа убрала напоминания: %s. Осталось: %d. Скажи ему коротко, что убрала.]' % ('; '.join(e.get('text') or _when(e['due']) for e in gone), len(items))
