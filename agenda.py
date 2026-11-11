"""What is on today / tomorrow: "что у меня на сегодня", "what's on today", "오늘 일정 뭐야", "今日の予定は". The program gathers what it really keeps for him (reminders that
fall on that day, dated moments, the to-do list) and hands her the list; she only retells it and never invents plans. Read-only. In ru, en, ko and ja."""
import re
import time

_ASK = [
    re.compile(r'(?i)\b(?:что|какие|какой|чем)\b.{0,24}(?:на сегодня|на завтра|в планах|заняться (?:сегодня|завтра))|(?:мои |наши )?(?:планы|дела) на (?:сегодня|завтра)|план на (?:сегодня|завтра)|что (?:у меня )?(?:сегодня|завтра)\b.{0,12}(?:запланировано|по плану|по делам)'),
    re.compile(r'(?i)what.?s (?:on )?(?:for )?(?:today|tomorrow)\b|what do i have (?:today|tomorrow|on)\b|my (?:plans|agenda|schedule|to-?dos?) (?:for )?(?:today|tomorrow)|what.?s on my (?:plate|schedule|agenda)|what.?s planned|what.?s my day'),
    re.compile(r'(?:오늘|내일).{0,8}(?:일정|할 ?일|계획|스케줄)|(?:일정|계획|스케줄).{0,8}(?:뭐|알려|뭔지)'),
    re.compile(r'(?:今日|明日|あした|きょう)の(?:予定|やること|スケジュール|タスク)|予定は(?:何|なに)|スケジュールを教えて'),
]
_TOMORROW = re.compile(r'(?i)завтра|tomorrow|내일|明日|あした')


def asks(text):
    text = str(text or '')[:300]
    return any(rx.search(text) for rx in _ASK)


def _day_start(t):
    lt = time.localtime(t)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def hint(text, reminders, moments, todo, now=None, habits_left=None):
    """The note for her with the plan of that day, or '' when he did not ask."""
    if not asks(text):
        return ''
    now = now or time.time()
    tomorrow = bool(_TOMORROW.search(str(text)))
    start = _day_start(now) + (86400 if tomorrow else 0)
    word = 'завтра' if tomorrow else 'сегодня'
    parts = []
    due = sorted([e for e in reminders if start <= e['due'] < start + 86400], key=lambda e: e['due'])
    if due:
        parts.append('напоминания: ' + '; '.join('%s%s' % (time.strftime('%H:%M', time.localtime(e['due'])), ' ' + e['text'] if e.get('text') else '') for e in due))
    dated = [m['text'] for m in moments if m.get('due') and start <= _day_start(m['due']) < start + 86400]
    if dated:
        parts.append('даты и договорённости: ' + '; '.join(dated))
    if todo:
        parts.append('список дел (без срока): ' + '; '.join(todo[:10]) + (' и ещё %d' % (len(todo) - 10) if len(todo) > 10 else ''))
    if habits_left and not tomorrow:
        parts.append('привычки, которые сегодня ещё не отмечены: ' + '; '.join(habits_left[:6]))
    if not parts:
        return ('[Он спросил про планы на %s: у программы ничего не записано (ни напоминаний, ни дат, ни списка дел). Скажи это честно и по-своему, '
                'ничего не выдумывай; можно предложить записать что-нибудь, если он захочет.]' % word)
    return ('[Он спросил про планы на %s. Вот всё, что программа хранит для него: %s. Перескажи это коротко и тепло, своими словами, ничего не добавляя от себя '
            'и не выдумывая дел.]' % (word, '. '.join(parts)))
