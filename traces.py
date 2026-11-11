"""Stack traces and failed tests, read by the program.
When the creator's message (or a command output / log that arrives as a message) holds a stack trace or a test-runner summary, the program parses it
and puts a short analysis next to the message: the exception and its root cause, the chain of "caused by", the frame in HIS code (not a library),
the usual cause of that kind of error, which tests failed and how many passed. She uses it as a head start and asks to see the file with [read:]
instead of guessing. Understands Python, Java/Kotlin, Node/JavaScript, .NET, Go and Rust traces; pytest, jest, dotnet test and go test summaries."""
import re

import devtools

MAX_REPORT = 2600

LIB_PATH = re.compile(r'(site-packages|dist-packages|node_modules|<frozen|[\\/]lib[\\/]python|[\\/]usr[\\/]lib|[\\/]rustc[\\/]|[\\/]\.cargo[\\/]|[\\/]go[\\/]src[\\/]|[\\/]\.nuget[\\/]|internal[\\/]|<string>|<stdin>)', re.I)
LIB_NAME = re.compile(r'^(java\.|javax\.|jdk\.|sun\.|com\.sun\.|kotlin\.|kotlinx\.|org\.springframework|org\.apache|org\.hibernate|org\.junit|io\.netty|System\.|Microsoft\.|runtime\.|std::|core::|alloc::|tokio::|node:|internal/)')

PY_FRAME = re.compile(r'^\s*File "([^"]+)", line (\d+)(?:, in (.+))?$')
PY_EXC = re.compile(r'^([A-Za-z_][\w.]*(?:Error|Exception|Warning|Exit|Interrupt|Fault)|[A-Za-z_][\w.]*\.[A-Z]\w*): ?(.*)$|^([A-Z]\w*(?:Error|Exception|Interrupt)|KeyboardInterrupt|StopIteration|SystemExit)$')
JAVA_HEAD = re.compile(r'^(?:Exception in thread "[^"]+" |Caused by: )?((?:[a-z_][\w]*\.)+[A-Z]\w*(?:Exception|Error)|[A-Z]\w*(?:Exception|Error))(?:: (.*))?$')
JAVA_AT = re.compile(r'^\s+at ([\w$.<>]+)\(([^)]*)\)')
JS_HEAD = re.compile(r'^((?:Uncaught )?(?:[A-Z]\w*Error|Error|AggregateError)): (.*)$')
JS_AT = re.compile(r'^\s+at (?:(.+?) \()?((?:file://|[A-Za-z]:\\|/|\.{0,2}/|node:)?[^():]+?):(\d+):(\d+)\)?$')
NET_HEAD = re.compile(r'^((?:[A-Z]\w+\.)+[A-Z]\w*Exception): (.*)$')
NET_AT = re.compile(r'^\s+at ([\w.`<>+,\[\]$ ]+)\(.*?\)(?: in (.+?):line (\d+))?$')
GO_PANIC = re.compile(r'^panic: (.*)$')
GO_FRAME = re.compile(r'^\s+(/[^\s:]+\.go|[A-Za-z]:\\[^\s:]+\.go):(\d+)')
RUST_PANIC = re.compile(r"^thread '([^']*)' panicked at (?:([^:]+):(\d+):\d+:?|'([^']*)', ([^:]+):(\d+):\d+)(.*)$")

# (pattern over "Type: message", advice)
ADVICE = [
    (r'NoneType.*(attribute|subscriptable|iterable|not callable)|Cannot read propert(y|ies) of (undefined|null)|NullPointerException|NullReferenceException',
     'пустое значение там, где ждали объект: найди, откуда оно пришло (функция вернула None/null, не заполнено поле, ключ не нашёлся), и проверь это место, а не строку падения'),
    (r'KeyError|IndexError|IndexOutOfBounds|ArgumentOutOfRange|KeyNotFound', 'обращение к ключу или индексу, которых нет: проверь данные на входе и пустые коллекции'),
    (r'ModuleNotFoundError|ImportError|Cannot find module|ClassNotFound|NoClassDefFound|FileNotFoundException.*dll|Could not load file or assembly',
     'не найден модуль или библиотека: не установлена зависимость, не то окружение (venv, версия Node/JDK) или опечатка в имени; сверь версию и путь запуска'),
    (r'ConnectionRefused|ECONNREFUSED|Connection refused|ConnectException|SocketException|WinError 10061', 'соединение отказано: сервис не запущен, не тот порт или адрес (localhost против контейнера), брандмауэр'),
    (r'TimeoutError|ETIMEDOUT|SocketTimeout|timed out|TimeoutException|DeadlineExceeded', 'таймаут: сервис медленный или недоступен; проверь сеть, пул соединений и размер таймаута, а не просто увеличивай его'),
    (r'CERTIFICATE_VERIFY_FAILED|SSLError|SSLHandshake|UNABLE_TO_VERIFY_LEAF_SIGNATURE|certificate', 'ошибка сертификата TLS: просрочен или чужой корневой сертификат (прокси компании), не отключай проверку, а добавь доверенный сертификат'),
    (r'PermissionError|EACCES|AccessDenied|UnauthorizedAccess|Permission denied', 'нет прав: проверь владельца и права файла или папки, запуск от нужного пользователя, занятый другим процессом файл'),
    (r'EADDRINUSE|Address already in use|address already in use|BindException|WinError 10048', 'порт занят: другой процесс или прошлый запуск не закрылся; найди процесс на этом порту или смени порт'),
    (r'MemoryError|OutOfMemoryError|heap out of memory|ENOMEM|OutOfMemoryException', 'не хватает памяти: утечка или слишком большие данные; смотри, что копится, и читай данными по частям'),
    (r'RecursionError|StackOverflowError|Maximum call stack|StackOverflowException', 'бесконечная или слишком глубокая рекурсия: проверь условие выхода'),
    (r'UnicodeDecodeError|UnicodeEncodeError|MalformedInput|invalid byte sequence', 'кодировка: файл не в той кодировке, которую ждёт код; укажи кодировку явно (utf-8)'),
    (r'JSONDecodeError|Unexpected token|SyntaxError: JSON|JsonReaderException|JsonParseException|invalid character', 'не разбирается JSON: пустой ответ, HTML вместо JSON (ошибка сервера) или обрезанные данные; посмотри сырой ответ'),
    (r'SyntaxError|IndentationError|TabError|ParseError|CS\d{4}', 'синтаксическая ошибка: смотри строку и предыдущую (незакрытая скобка или кавычка часто ломает следующую)'),
    (r'TypeError.*(unsupported operand|not supported between|must be str|argument)|InvalidCastException|ClassCastException|ValueError.*(invalid literal|could not convert)',
     'не тот тип данных: число приходит строкой или наоборот; проверь, что именно попало в значение (напечатай тип)'),
    (r'AttributeError|NoSuchMethod|is not a function|MissingMethod', 'у объекта нет такого атрибута или метода: другая версия библиотеки, опечатка или объект не того типа'),
    (r'ConcurrentModification|RuntimeError.*(changed size during iteration|Event loop|no running event loop)|InvalidOperationException.*(Collection was modified)', 'изменение коллекции во время обхода или проблема с циклом событий: обходи копию, не смешивай синхронный и асинхронный код'),
    (r'IntegrityError|DuplicateKey|UNIQUE constraint|ConstraintViolation|violates .* constraint|SqlException.*(duplicate|constraint)', 'нарушено ограничение БД: дубликат ключа или ссылка на несуществующую запись; смотри значение, которое вставляли'),
    (r'OperationalError.*(locked|no such table|no such column)|relation .* does not exist|Table .* doesn.t exist', 'проблема со схемой БД: не накатили миграцию, не та база или файл базы заблокирован другим процессом'),
    (r'ZeroDivisionError|DivideByZero|ArithmeticException', 'деление на ноль: проверь знаменатель до деления (пустые данные, нулевой счётчик)'),
    (r'401|403|Unauthorized|Forbidden', 'нет доступа: истёк или неверный токен, нет нужной роли; проверь заголовок авторизации (значение сюда не присылай)'),
    (r'AssertionError|AssertionFailedError|expect\(|Expected .* but', 'не выполнилось ожидание теста: сравни ожидаемое и фактическое значение; проверь, что изменилось в коде или в тестовых данных'),
]
ADVICE = [(re.compile(p, re.I), a) for p, a in ADVICE]


def _clip(s, n=160):
    s = s.strip()
    return s if len(s) <= n else s[:n - 1] + '…'


def python_traces(lines):
    out, i = [], 0
    while i < len(lines):
        if 'Traceback (most recent call last):' in lines[i]:
            frames, j = [], i + 1
            while j < len(lines):
                m = PY_FRAME.match(lines[j])
                if m:
                    frames.append((m.group(1), int(m.group(2)), m.group(3) or ''))
                    j += 1
                    while j < len(lines) and lines[j].startswith('    '):   # source line and ^^^^ markers
                        j += 1
                    continue
                break
            exc, msg = '', ''
            if j < len(lines):
                m = PY_EXC.match(lines[j].strip())
                if m:
                    exc, msg = (m.group(1) or m.group(3) or ''), (m.group(2) or '')
                    j += 1
            if exc or frames:
                out.append({'lang': 'Python', 'exc': exc or 'ошибка', 'msg': msg, 'frames': frames, 'innermost_last': True})
            i = j
        else:
            i += 1
    return out


def java_traces(lines):
    out, cur = [], None
    for line in lines:
        m = JAVA_AT.match(line)
        if m and cur is not None:
            loc = m.group(2)
            fm = re.match(r'([^:]+):(\d+)', loc)
            cur['frames'].append((fm.group(1) if fm else '', int(fm.group(2)) if fm else 0, m.group(1)))
            continue
        h = JAVA_HEAD.match(line.strip())
        if h and not line.startswith(' ') or (h and line.strip().startswith('Caused by:')):
            cur = {'lang': 'Java/Kotlin', 'exc': h.group(1), 'msg': h.group(2) or '', 'frames': [], 'innermost_last': False, 'caused': line.strip().startswith('Caused by:')}
            out.append(cur)
    return [t for t in out if t['frames']]


def js_traces(lines):
    out, cur = [], None
    for line in lines:
        m = JS_AT.match(line)
        if m and cur is not None:
            cur['frames'].append((m.group(2), int(m.group(3)), m.group(1) or ''))
            continue
        h = JS_HEAD.match(line.strip())
        if h and not line.startswith(' '):
            cur = {'lang': 'JavaScript', 'exc': h.group(1).replace('Uncaught ', ''), 'msg': h.group(2), 'frames': [], 'innermost_last': False}
            out.append(cur)
    return [t for t in out if t['frames']]


def net_traces(lines):
    out, cur = [], None
    for line in lines:
        m = NET_AT.match(line)
        if m and cur is not None:
            cur['frames'].append((m.group(2) or m.group(1), int(m.group(3) or 0), m.group(1)))
            continue
        h = NET_HEAD.match(line.strip())
        if h and not line.startswith(' '):
            cur = {'lang': '.NET', 'exc': h.group(1), 'msg': h.group(2), 'frames': [], 'innermost_last': False}
            out.append(cur)
    return [t for t in out if t['frames']]


def go_traces(lines):
    out = []
    for i, line in enumerate(lines):
        m = GO_PANIC.match(line)
        if m:
            frames = []
            for j in range(i + 1, min(i + 60, len(lines))):
                f = GO_FRAME.match(lines[j])
                if f:
                    func = lines[j - 1].strip().split('(')[0] if j > 0 else ''
                    frames.append((f.group(1), int(f.group(2)), func))
            out.append({'lang': 'Go', 'exc': 'panic', 'msg': m.group(1), 'frames': frames, 'innermost_last': False})
    return out


def rust_traces(lines):
    out = []
    for i, line in enumerate(lines):
        m = RUST_PANIC.match(line)
        if m:
            path, no = (m.group(2), m.group(3)) if m.group(2) else (m.group(5), m.group(6))
            msg = (lines[i + 1].strip() if i + 1 < len(lines) else '') if m.group(2) else (m.group(4) or '')
            out.append({'lang': 'Rust', 'exc': 'panic', 'msg': msg, 'frames': [(path, int(no), '')], 'innermost_last': False})
    return out


def detect(text):
    """All stack traces found in a text: [{'lang','exc','msg','frames':[(path,line,func)],'innermost_last'}]."""
    lines = text.replace('\r\n', '\n').split('\n')[:3000]
    found = []
    for fn in (python_traces, java_traces, js_traces, net_traces, go_traces, rust_traces):
        found += fn(lines)
    return found


def culprit(t):
    """The innermost frame that is in his own code, or None."""
    for path, line, func in (reversed(t['frames']) if t['innermost_last'] else t['frames']):
        if not (path or func) or LIB_PATH.search(path or '') or LIB_NAME.match(func or '') or LIB_NAME.match(path or ''):
            continue
        return path, line, func
    return None


def advice(t):
    subject = '%s: %s' % (t['exc'], t['msg'])
    for rx, text in ADVICE:
        if rx.search(subject):
            return text
    return ''


# ---- test runner summaries ----

PYTEST_SUM = re.compile(r'=+ (?:(\d+) failed)?,? ?(?:(\d+) passed)?,? ?(?:(\d+) skipped)?,? ?(?:(\d+) errors?)?.*? in ([\d.]+)s')
PYTEST_FAIL = re.compile(r'^(FAILED|ERROR) (\S+?)(?: - (.*))?$')
JEST_SUM = re.compile(r'^Tests:\s+(.*)$')
JEST_FAIL = re.compile(r'^\s*● (.+?)$')
DOTNET_SUM = re.compile(r'(?:Failed!|Passed!)\s+-\s+Failed:\s*(\d+), Passed:\s*(\d+), Skipped:\s*(\d+)')
DOTNET_FAIL = re.compile(r'^\s*Failed (\S+)')
GO_FAIL = re.compile(r'^--- FAIL: (\S+)')


def test_summary(text):
    """A one-paragraph summary of a test run, or ''."""
    lines = text.replace('\r\n', '\n').split('\n')[:5000]
    parts = []
    fails = [(m.group(2), m.group(3) or '') for m in (PYTEST_FAIL.match(l) for l in lines) if m]
    s = next((m for m in (PYTEST_SUM.search(l) for l in lines) if m and any(m.groups()[:4])), None)
    if s or fails:
        nums = [('провалено', s.group(1)), ('прошло', s.group(2)), ('пропущено', s.group(3)), ('с ошибкой', s.group(4))] if s else []
        head = 'pytest: ' + ', '.join('%s %s' % (k, v) for k, v in nums if v) + (' за %s с' % s.group(5) if s else '')
        parts.append(head + ('. Упавшие: ' + '; '.join('%s%s' % (n, ' (' + _clip(why, 100) + ')' if why else '') for n, why in fails[:8]) if fails else ''))
    j = next((m.group(1) for m in (JEST_SUM.match(l) for l in lines) if m), None)
    if j:
        names = []
        for l in lines:
            m = JEST_FAIL.match(l)
            if m and m.group(1) not in names:
                names.append(m.group(1))
        parts.append('jest: ' + j + ('. Упавшие: ' + '; '.join(_clip(n, 100) for n in names[:8]) if names else ''))
    d = next((m for m in (DOTNET_SUM.search(l) for l in lines) if m), None)
    if d:
        names = [m.group(1) for m in (DOTNET_FAIL.match(l) for l in lines) if m]
        parts.append('dotnet test: провалено %s, прошло %s, пропущено %s' % d.groups() + ('. Упавшие: ' + '; '.join(names[:8]) if names else ''))
    g = [m.group(1) for m in (GO_FAIL.match(l) for l in lines) if m]
    if g:
        parts.append('go test: упавшие: ' + '; '.join(g[:8]))
    return '\n'.join(parts)


# ---- the analysis next to the message ----

def analyze(text):
    """Analysis of the stack traces and test runs inside a message, '' when there is nothing to analyse."""
    if not isinstance(text, str) or len(text) < 40:
        return ''
    found = detect(text)
    summary = test_summary(text)
    if not found and not summary:
        return ''
    out = ['Разбор программы (она прочитала стек и вывод тестов; опирайся на него, не пересказывай всё подряд, а скажи главное: где ломается, почему вероятнее всего и что проверить первым).']
    if summary:
        out.append(summary)
    seen = set()
    shown = 0
    for t in found:
        key = (t['exc'], t['msg'], len(t['frames']))
        if key in seen:
            continue
        seen.add(key)
        if shown >= 3:
            break
        shown += 1
        head = '%s: %s%s' % (t['lang'], t['exc'], (': ' + _clip(devtools.mask_secrets(t['msg']))) if t['msg'] else '')
        c = culprit(t)
        where = ' Падение в его коде: %s:%d%s.' % (c[0].replace('\\', '/').split('/')[-1] if c[0] else '?', c[1], (' в ' + _clip(c[2], 60)) if c[2] else '') if c else \
                ' В стеке нет его кода: ошибка внутри библиотеки или рантайма, ищи, что ей передали, и версии.'
        tip = advice(t)
        out.append(head + '.' + where + (' Обычно это: ' + tip + '.' if tip else '') + (' Это причина других ошибок выше.' if t.get('caused') else ''))
    if len(found) > shown:
        out.append('Других похожих ошибок в тексте: %d.' % (len(found) - shown))
    out.append('Файл с этой строкой покажи себе через [read:имя файла], если нужен контекст.')
    return _clip('\n'.join(out), MAX_REPORT)
