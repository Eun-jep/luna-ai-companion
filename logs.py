"""A service log, read by the program down to the cause.
When the creator's message holds a log (many lines with levels or timestamps), the program finds what a tired person misses at 3 a.m.:
the FIRST real problem (the loud errors at the end are usually its echo), what warned about it just before, when it began, which lines repeat
and how often, and the usual cause of that kind of error. The result goes next to the message as a head start; nothing is run, stopped or
restarted, and secrets in the lines are masked. Stack traces inside the log are left to traces.py."""
import re

import devtools
import traces

MAX_REPORT = 2400
MIN_LINES = 6

STAMP = re.compile(r'^\W{0,2}(\d{4}[-/.]\d{2}[-/.]\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?|\d{2}:\d{2}:\d{2}(?:[.,]\d+)?|[A-Z][a-z]{2} +\d{1,2} \d{2}:\d{2}:\d{2}|\d{2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2})')
LEVEL = re.compile(r'(?<![A-Za-z])(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|ERR|FATAL|CRITICAL|CRIT|PANIC|SEVERE|EMERG)(?![A-Za-z])')
SEVERITY = {'TRACE': 0, 'DEBUG': 0, 'INFO': 1, 'NOTICE': 1, 'WARN': 2, 'WARNING': 2, 'ERROR': 3, 'ERR': 3, 'SEVERE': 3, 'FATAL': 4, 'CRITICAL': 4, 'CRIT': 4, 'PANIC': 4, 'EMERG': 4}
# a line that is bad even with no level word (plain stderr, systemd, docker, nginx)
BAD = re.compile(r'(?i)(exception|traceback|failed|failure|refused|denied|timed? ?out|cannot|can.t |unable to|no such|not found|killed|oom|segfault|panic|fatal|abort|crash|exit(?:ed)? (?:with )?(?:code|status) [1-9]|unhealthy|disk full|no space left)')
NUM = re.compile(r'0x[0-9a-fA-F]+|\b\d+(?:[.:,-]\d+)*\b|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

CAUSES = [   # beyond traces.ADVICE: what service logs say in words
    (re.compile(r'(?i)out of memory|oom.kill|killed process|cannot allocate memory|exit(?:ed)? (?:with )?code 137'), 'процесс убит из-за нехватки памяти (OOM): смотри лимит памяти контейнера или службы и что растёт перед этим'),
    (re.compile(r'(?i)no space left on device|disk full|ENOSPC|database or disk is full'), 'кончилось место на диске: найди, что заняло (логи, временные файлы, тома Docker), и освободи до перезапуска'),
    (re.compile(r'(?i)too many open files|EMFILE|file descriptor'), 'кончились файловые дескрипторы: утечка соединений или файлов, или слишком низкий лимит открытых файлов'),
    (re.compile(r'(?i)name or service not known|getaddrinfo|ENOTFOUND|could not resolve|no such host|temporary failure in name resolution'), 'имя не разрешается (DNS): опечатка в адресе, нет сети в контейнере или не тот резолвер'),
    (re.compile(r'(?i)connection pool|too many connections|remaining connection slots|pool exhausted|timeout waiting for connection'), 'исчерпан пул или лимит соединений с базой: утечка соединений, долгие запросы или слишком много воркеров'),
    (re.compile(r'(?i)deadlock'), 'взаимная блокировка в базе: две транзакции берут одни и те же строки в разном порядке'),
    (re.compile(r'(?i)exit(?:ed)? (?:with )?(?:code|status) (?:[1-9]\d*)|main process exited|start request repeated too quickly|restart(?:ing)? loop|CrashLoopBackOff|back-?off'), 'служба падает при старте и перезапускается по кругу: причина в первой ошибке ДО первого перезапуска, а не в последующих'),
    (re.compile(r'(?i)health ?check.*fail|unhealthy|readiness probe failed|liveness probe failed'), 'проба здоровья не проходит: служба поднялась, но не отвечает на проверочный адрес или не успевает до таймаута пробы'),
    (re.compile(r'(?i)(unauthorized|authentication failed|invalid (api )?(token|credentials)|401)'), 'отказ в доступе: токен или пароль устарели или неверны (значения сюда не присылай)'),
]


def _level(line):
    m = LEVEL.search(line[:120])
    return SEVERITY[m.group(1)] if m else None


def _norm(line):
    """The line without time, level and numbers: the same message with other ids counts once."""
    line = STAMP.sub('', line.strip())
    line = LEVEL.sub('', line, count=1)
    line = NUM.sub('#', line)
    return ' '.join(line.split())[:140]


def parse(text):
    """-> [(index, stamp, severity, text)] of the lines that look like log lines."""
    out = []
    for i, line in enumerate(str(text).splitlines()):
        if not line.strip():
            continue
        m = STAMP.match(line)
        lvl = _level(line)
        out.append((i, m.group(1) if m else '', lvl, line.strip()))
    return out


def looks_like_log(text):
    if not isinstance(text, str) or text.count('\n') < MIN_LINES - 1:
        return False
    rows = parse(text)
    marked = sum(1 for r in rows if r[1] or r[2] is not None)
    return len(rows) >= MIN_LINES and marked >= max(4, len(rows) // 2)


def _cause(line):
    for rx, tip in CAUSES:
        if rx.search(line):
            return tip
    for rx, tip in traces.ADVICE:
        if rx.search(line):
            return tip
    return ''


def analyze(text):
    """The short reading of a log placed next to the message; '' when the message holds no log."""
    if not looks_like_log(text):
        return ''
    rows = parse(text)
    counts = {}
    for _, _, lvl, _ in rows:
        key = lvl if lvl is not None else -1
        counts[key] = counts.get(key, 0) + 1
    problems = [r for r in rows if (r[2] is not None and r[2] >= 3) or (r[2] is None and BAD.search(r[3]))]
    names = {0: 'debug', 1: 'info', 2: 'warn', 3: 'error', 4: 'fatal'}
    summary = ', '.join('%s %d' % (names[k], counts[k]) for k in sorted(counts) if k >= 0)
    stamps = [r[1] for r in rows if r[1]]
    span = (' С %s по %s.' % (stamps[0], stamps[-1])) if len(stamps) >= 2 else ''
    out = ['Разбор лога программой (она прочитала его целиком и ничего не запускала; опирайся на него: назови первую настоящую проблему, '
           'вероятную причину и что проверить первым; не пересказывай лог построчно).']
    out.append('Строк %d: %s.%s' % (len(rows), summary or 'без уровней', span))
    if not problems:
        out.append('Ошибок и явных сбоев в этом куске нет. Если проблема есть, она либо раньше этого куска, либо в другом логе: попроси кусок до первого сбоя.')
        return traces._clip('\n'.join(out), MAX_REPORT)
    first = problems[0]
    before = [r for r in rows if r[0] < first[0] and r[2] == 2][-2:]
    out.append('Первая проблема (строка %d%s): %s' % (first[0] + 1, ', ' + first[1] if first[1] else '', traces._clip(devtools.mask_secrets(first[3]), 200)))
    if before:
        out.append('Перед ней предупреждали: ' + ' | '.join(traces._clip(devtools.mask_secrets(r[3]), 120) for r in before))
    tip = _cause(first[3])
    if tip:
        out.append('Обычно это: ' + tip + '.')
    groups = {}
    for r in problems:
        groups.setdefault(_norm(r[3]), []).append(r)
    echoes = sorted(((len(v), k, v) for k, v in groups.items()), key=lambda t: -t[0])[:3]
    reps = [(n, k) for n, k, v in echoes if n >= 3 and v[0][0] != first[0]]
    if reps:
        out.append('Что повторяется: ' + '; '.join('%d× «%s»' % (n, traces._clip(devtools.mask_secrets(k), 100)) for n, k in reps) + '. Это, скорее всего, следствие, а не причина.')
    if len(problems) > 1 and problems[-1][0] - first[0] > 5:
        out.append('Между первой проблемой и последней строк: %d: самый громкий шум в конце, причину ищи в начале.' % (problems[-1][0] - first[0]))
    tail = rows[-1]
    out.append('Последняя строка: ' + traces._clip(devtools.mask_secrets(tail[3]), 140))
    out.append('Нужен контекст — попроси фрагмент до строки %d или конфиг службы. Перезапускать и менять что-то она сама не будет.' % (first[0] + 1))
    return traces._clip('\n'.join(out), MAX_REPORT)
