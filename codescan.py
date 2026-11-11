"""Her hands, part 7: an audit of a whole code project, computed by the program, not guessed by the model.
She asks for it ([scan:project]); the creator presses; the program walks the project folder of the file she was last shown and reports
what it measured: languages and size, hardcoded secrets (file and line only: the value is never printed), risky calls, broken Python files,
dependency hygiene, Docker and CI mistakes, the biggest and most complex functions, TODO counts. Read-only; skips dependencies, build output
and hidden folders; reads at most a few thousand files; every number in the report is exact for what was scanned."""
import ast
import json
import os
import re
import secrets
import time
from pathlib import Path

import devtools
import infra
import runner

TTL = 120
PENDING = {}
MAX_FILES, MAX_BYTES, MAX_SECONDS, MAX_LINE = 4000, 1 << 20, 20, 2000
SKIP_DIRS = devtools.CODE_SKIP | {'node_modules', 'venv', '.venv', 'env', 'vendor', '__pycache__', 'site-packages', 'target', 'out', 'coverage', 'packages', 'third_party'}
LANG = {'.py': 'Python', '.js': 'JavaScript', '.mjs': 'JavaScript', '.jsx': 'JavaScript', '.ts': 'TypeScript', '.tsx': 'TypeScript', '.cs': 'C#',
        '.java': 'Java', '.kt': 'Kotlin', '.go': 'Go', '.rs': 'Rust', '.cpp': 'C++', '.cc': 'C++', '.c': 'C', '.h': 'C/C++', '.hpp': 'C++', '.php': 'PHP',
        '.rb': 'Ruby', '.swift': 'Swift', '.sql': 'SQL', '.sh': 'Shell', '.ps1': 'PowerShell', '.html': 'HTML', '.css': 'CSS', '.vue': 'Vue'}
CONFIG_EXT = {'.yml', '.yaml', '.json', '.toml', '.ini', '.cfg', '.xml', '.gradle', '.properties', '.tf', '.conf'}
SECRET_FILE = re.compile(r'(^\.env(\.|$)|\.pem$|\.pfx$|\.p12$|id_rsa|\.keystore$)', re.I)
SAFE_FILE = re.compile(r'(example|sample|template|dist)', re.I)

PLACEHOLDER = re.compile(r'(?i)(change.?me|example|your[_-]|xxx|<[^>]+>|\$\{|\{\{|os\.environ|getenv|process\.env|placeholder|dummy|test|todo|\*{3,}|password$|secret$)')
SECRETS = [
    ('AWS access key', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('private key', re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----')),
    ('GitHub token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36,}\b')),
    ('Slack token', re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{10,}')),
    ('Google API key', re.compile(r'\bAIza[0-9A-Za-z_-]{35}\b')),
    ('connection string with password', re.compile(r'(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:/@"\']+:[^\s@"\']{3,}@')),
]
ASSIGN = re.compile(r'(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret)\w*["\']?\s*[:=]\s*["\']([^"\'\s]{8,})["\']')

# (language set, severity, what, pattern); '*' = any code file
RISKS = [
    ({'.py'}, 'high', 'eval/exec on data', re.compile(r'(?<![\w.])(?:eval|exec)\(')),
    ({'.py'}, 'high', 'shell=True', re.compile(r'shell\s*=\s*True')),
    ({'.py'}, 'high', 'pickle on untrusted data', re.compile(r'\bpickle\.loads?\(')),
    ({'.py'}, 'medium', 'yaml.load without a safe loader', re.compile(r'\byaml\.load\((?!.*Safe)')),
    ({'.py'}, 'high', 'SQL built from strings', re.compile(r'\.execute(?:many)?\(\s*(?:f["\']|["\'][^"\']*["\']\s*(?:\+|%\s*[\w(]))')),
    ({'.py'}, 'medium', 'TLS verification off', re.compile(r'verify\s*=\s*False')),
    ({'.py'}, 'medium', 'debug mode on', re.compile(r'(?m)^\s*(?:app\.run\(.*debug\s*=\s*True|DEBUG\s*=\s*True)')),
    ({'.py', '.js', '.ts', '.java', '.cs', '.go', '.php'}, 'medium', 'weak hash (MD5/SHA-1)', re.compile(r'(?i)\b(?:md5|sha1)\b\s*[\(.]|MessageDigest\.getInstance\(\s*"(?:MD5|SHA-?1)"|MD5\.Create|SHA1\.Create')),
    ({'.js', '.jsx', '.ts', '.tsx', '.vue'}, 'high', 'eval or new Function', re.compile(r'(?<![\w.])eval\(|new Function\(')),
    ({'.js', '.jsx', '.ts', '.tsx', '.vue', '.html'}, 'medium', 'innerHTML / document.write (XSS risk)', re.compile(r'\.innerHTML\s*=|document\.write\(|dangerouslySetInnerHTML')),
    ({'.js', '.ts', '.mjs'}, 'high', 'command execution from a string', re.compile(r'child_process\.exec(?:Sync)?\(|\bexec(?:Sync)?\(\s*`')),
    ({'.js', '.ts', '.mjs', '.go'}, 'medium', 'TLS verification off', re.compile(r'rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true')),
    ({'.js', '.ts', '.mjs', '.py', '.java', '.cs', '.go', '.php'}, 'medium', 'CORS open to everyone', re.compile(r'(?i)access-control-allow-origin["\']?\s*[:,]\s*["\']?\*|allow_origins\s*=\s*\[\s*["\']\*|AllowAnyOrigin')),
    ({'.java', '.cs'}, 'high', 'insecure deserialization', re.compile(r'\bBinaryFormatter\b|\bObjectInputStream\b')),
    ({'.java'}, 'high', 'Runtime.exec', re.compile(r'Runtime\.getRuntime\(\)\.exec\(')),
    ({'.php'}, 'high', 'eval / system calls', re.compile(r'\b(?:eval|system|shell_exec|passthru)\(')),
    ({'.c', '.cc', '.cpp', '.h'}, 'high', 'unbounded C string function', re.compile(r'\b(?:strcpy|strcat|sprintf|gets)\(')),
]
TODO_RE = re.compile(r'\b(TODO|FIXME|HACK|XXX)\b')


def _walk(root):
    """Files of the project: [(path, relative name)] with the skip rules applied, bounded in count and time."""
    out, started = [], time.time()
    stack = [root]
    while stack and len(out) < MAX_FILES and time.time() - started < MAX_SECONDS:
        folder = stack.pop()
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            low = e.name.lower()
            try:
                if e.is_dir(follow_symlinks=False):
                    if low not in SKIP_DIRS and not (low.startswith('.') and low not in ('.github', '.gitlab', '.circleci')):
                        stack.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    out.append((e.path, os.path.relpath(e.path, root).replace('\\', '/')))
            except OSError:
                continue
    return out, len(out) >= MAX_FILES


def _text(path):
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        raw = open(path, 'rb').read()
    except OSError:
        return None
    if b'\x00' in raw[:2000]:
        return None
    return raw.decode('utf-8', errors='replace')


def _funcs(tree):
    """(name, line, length, branches) of every function in a Python module."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, 'end_lineno', node.lineno)
            branches = 1 + sum(isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler, ast.BoolOp, ast.IfExp, ast.comprehension)) for n in ast.walk(node))
            out.append((node.name, node.lineno, end - node.lineno + 1, branches))
    return out


def _deps(rel, text, notes):
    name = rel.rsplit('/', 1)[-1].lower()
    if name == 'requirements.txt' or (name.startswith('requirements') and name.endswith('.txt')):
        lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith(('#', '-'))]
        loose = [re.split(r'[<>=!~\[; ]', l)[0] for l in lines if '==' not in l]
        notes.append('%s: %d пакетов, без точной версии %d%s' % (rel, len(lines), len(loose), ' (' + ', '.join(loose[:8]) + ')' if loose else ''))
    elif name == 'package.json':
        try:
            data = json.loads(text)
        except ValueError:
            notes.append('%s: не читается как JSON' % rel)
            return
        deps, dev = data.get('dependencies') or {}, data.get('devDependencies') or {}
        loose = [k for k, v in {**deps, **dev}.items() if isinstance(v, str) and (v.strip() in ('*', 'latest', '') or v.startswith(('git', 'http')))]
        notes.append('%s: зависимостей %d, для разработки %d%s' % (rel, len(deps), len(dev), ', нестрогие версии: ' + ', '.join(loose[:8]) if loose else ''))
    elif name == 'go.mod':
        notes.append('%s: модулей %d' % (rel, len(re.findall(r'(?m)^\s*[\w./-]+\s+v\d', text))))
    elif name == 'cargo.toml':
        notes.append('%s: зависимостей %d' % (rel, len(re.findall(r'(?m)^[\w-]+\s*=\s*(?:"|\{)', text.split('[dependencies]', 1)[-1].split('\n[', 1)[0])) if '[dependencies]' in text else 0))
    elif name == 'pom.xml':
        notes.append('%s: зависимостей %d' % (rel, text.count('<dependency>')))
    elif name.endswith('.csproj'):
        notes.append('%s: пакетов NuGet %d' % (rel, text.count('<PackageReference')))


def _config_checks(rel, text, found):
    name = rel.rsplit('/', 1)[-1].lower()
    lines = text.splitlines()
    if name == 'dockerfile' or name.startswith('dockerfile.'):
        froms = [(i + 1, l) for i, l in enumerate(lines) if re.match(r'(?i)\s*FROM\s', l)]
        for i, l in froms:
            image = l.split()[1] if len(l.split()) > 1 else ''
            if image.lower() != 'scratch' and not image.startswith('$') and ('@' not in image and (':' not in image or image.endswith(':latest'))):
                found.append(('medium', rel, i, 'Docker: образ без фиксированной версии (' + image[:40] + ')'))
        if froms and not any(re.match(r'(?i)\s*USER\s+(?!root)', l) for l in lines):
            found.append(('medium', rel, froms[-1][0], 'Docker: нет USER, контейнер работает от root'))
        for i, l in enumerate(lines, 1):
            if re.search(r'(?i)(curl|wget)[^|]*\|\s*(sudo\s+)?(sh|bash)', l):
                found.append(('high', rel, i, 'Docker: скрипт из сети запускается сразу через оболочку'))
            if re.match(r'(?i)\s*ADD\s+https?://', l):
                found.append(('low', rel, i, 'Docker: ADD с URL (лучше COPY и проверка контрольной суммы)'))
    if rel.startswith('.github/workflows/') and name.endswith(('.yml', '.yaml')):
        for i, l in enumerate(lines, 1):
            if re.search(r'uses:\s*[\w./-]+@(master|main)\b', l):
                found.append(('medium', rel, i, 'CI: действие подключено по ветке, а не по версии'))
            if 'pull_request_target' in l:
                found.append(('high', rel, i, 'CI: pull_request_target запускается с секретами; не выполняй в нём код из форка'))
        if 'permissions:' not in text:
            found.append(('low', rel, 1, 'CI: не заданы permissions, токен получает права по умолчанию'))
    if name in ('docker-compose.yml', 'docker-compose.yaml', 'compose.yml'):
        for i, l in enumerate(lines, 1):
            if re.search(r'privileged:\s*true|network_mode:\s*["\']?host', l):
                found.append(('high', rel, i, 'compose: privileged или сеть host'))
            if re.search(r'(?i)(password|secret|token)\w*\s*[:=]\s*[^\s$\{][^\s]{5,}', l):
                found.append(('medium', rel, i, 'compose: пароль прямо в файле (лучше переменная окружения или секрет)'))


def scan(root):
    """Walk the project and measure it. Returns the report text."""
    files, cut = _walk(root)
    langs, risks, secrets_found, broken, todo, fn_rows, big, notes, hygiene = {}, [], [], [], 0, [], [], [], []
    names = {rel.lower() for _, rel in files}
    has_tests = any(re.search(r'(^|/)(tests?|__tests__|spec)(/|$)|(^|/)(test_[^/]+|[^/]+_test|[^/]+\.(test|spec))\.\w+$', rel) for rel in names)
    for path, rel in files:
        base = rel.rsplit('/', 1)[-1]
        ext = os.path.splitext(base.lower())[1]
        if SECRET_FILE.search(base) and not SAFE_FILE.search(base):
            hygiene.append('файл с секретами лежит в проекте: %s (содержимое не читалось; проверь, что он в .gitignore)' % rel)
            continue
        if devtools.SECRET_RE.search(base) and ext not in LANG:
            continue
        code, conf = ext in LANG, ext in CONFIG_EXT or base.lower().startswith(('dockerfile', 'docker-compose', 'requirements', 'compose'))
        if not code and not conf:
            continue
        text = _text(path)
        if text is None:
            continue
        lines = text.splitlines()
        is_test = bool(re.search(r'(^|/)(tests?|__tests__|spec|fixtures?)/|(^|/)test_[^/]+$|\.(test|spec)\.\w+$', rel))
        if code:
            loc = sum(1 for l in lines if l.strip())
            langs.setdefault(LANG[ext], [0, 0])
            langs[LANG[ext]][0] += 1
            langs[LANG[ext]][1] += loc
            big.append((len(lines), rel))
        for i, line in enumerate(lines, 1):
            if len(line) > MAX_LINE:
                continue
            for kind, rx in SECRETS:
                if rx.search(line):
                    secrets_found.append((rel, i, kind))
            m = None if is_test else ASSIGN.search(line)
            if m and not PLACEHOLDER.search(m.group(1)) and not PLACEHOLDER.search(line.split(m.group(1))[0][-30:]):
                secrets_found.append((rel, i, 'пароль/ключ в коде'))
            if code:
                for langs_set, sev, what, rx in RISKS:
                    if ext in langs_set and rx.search(line):
                        risks.append((sev, rel, i, what))
                if TODO_RE.search(line):
                    todo += 1
        if ext == '.py':
            try:
                tree = ast.parse(text)
            except SyntaxError as exc:
                broken.append('%s:%s' % (rel, exc.lineno or 1))
            except (ValueError, RecursionError):
                broken.append('%s' % rel)
            else:
                fn_rows += [(n, rel, ln, length, br) for n, ln, length, br in _funcs(tree)]
        _deps(rel, text, notes)
        _config_checks(rel, text, risks)
        risks += [(sev, rel, ln, what) for sev, ln, what in infra.lint(rel, text)]
    # project-level hygiene
    if '.gitignore' not in names:
        hygiene.append('нет .gitignore')
    if not any(n.startswith(('readme',)) for n in names):
        hygiene.append('нет README')
    if not has_tests and any(l in langs for l in ('Python', 'JavaScript', 'TypeScript', 'C#', 'Java', 'Go', 'Rust')):
        hygiene.append('тестов не найдено')
    if 'package.json' in names and not names & {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml'}:
        hygiene.append('package.json есть, а lock-файла нет: сборки не воспроизводимы')
    if any(n.endswith('requirements.txt') for n in names) and not names & {'poetry.lock', 'pipfile.lock', 'uv.lock'}:
        hygiene.append('зависимости Python без lock-файла (точность зависит от ==)')
    # the report
    out = ['АУДИТ ПРОЕКТА «%s» (посчитан программой: %d файлов просмотрено%s; секреты показаны только местом, значения не печатаются).' % (
        os.path.basename(root), len(files), ', дальше предел и просмотр остановлен' if cut else '')]
    if langs:
        rows = sorted(langs.items(), key=lambda kv: -kv[1][1])
        out.append('Языки: ' + '; '.join('%s: %d файлов, %d строк кода' % (k, v[0], v[1]) for k, v in rows[:8]))
    if secrets_found:
        shown = secrets_found[:12]
        out.append('СЕКРЕТЫ В КОДЕ (%d), опасно, если проект попадает в git:' % len(secrets_found))
        out += ['- %s:%d, %s' % s for s in shown]
        if len(secrets_found) > 12:
            out.append('- и ещё %d' % (len(secrets_found) - 12))
    else:
        out.append('Секретов в коде не найдено (проверены ключи облаков и токены, пароли в присваиваниях, строки подключения к БД).')
    if broken:
        out.append('Python-файлы, которые не разбираются (синтаксис): ' + ', '.join(broken[:10]))
    order = {'high': 0, 'medium': 1, 'low': 2}
    risks.sort(key=lambda r: (order[r[0]], r[1], r[2]))
    if risks:
        out.append('РИСКИ (%d: высоких %d, средних %d, низких %d):' % (len(risks), *(sum(r[0] == s for r in risks) for s in ('high', 'medium', 'low'))))
        out += ['- [%s] %s:%d, %s' % (sev, rel, ln, what) for sev, rel, ln, what in risks[:20]]
        if len(risks) > 20:
            out.append('- и ещё %d' % (len(risks) - 20))
    else:
        out.append('Рискованных вызовов и ошибок в Docker/CI не найдено.')
    if notes:
        out.append('Зависимости: ' + ' | '.join(notes[:8]))
    if hygiene:
        out.append('Гигиена проекта: ' + '; '.join(hygiene[:10]))
    if fn_rows:
        longest = sorted(fn_rows, key=lambda r: -r[3])[:6]
        tangled = sorted(fn_rows, key=lambda r: -r[4])[:6]
        out.append('Самые длинные функции Python: ' + '; '.join('%s (%s:%d, %d строк)' % (n, rel, ln, length) for n, rel, ln, length, _ in longest))
        out.append('Самые разветвлённые (ветвлений): ' + '; '.join('%s (%s:%d, %d)' % (n, rel, ln, br) for n, rel, ln, _, br in tangled))
    if big:
        out.append('Самые большие файлы: ' + '; '.join('%s (%d строк)' % (rel, n) for n, rel in sorted(big, reverse=True)[:6]))
    if todo:
        out.append('Пометок TODO/FIXME/HACK: %d' % todo)
    out.append('Дальше: попроси её разобрать самые опасные места по одному (покажи файл через [read:]), а проверку зависимостей на уязвимости запусти там, где есть инструмент (pip-audit, npm audit).')
    return '\n'.join(out)


# ---- the plate and the press ----

def propose(arg=''):
    """A plate for the project folder of the file she was last shown: {'token','project'}, {'fail': 'noproject'} when unclear."""
    root = runner.project_dir()
    if not root:
        return {'fail': 'noproject'}
    now = time.time()
    for k in [k for k, v in PENDING.items() if now - v[1] > TTL]:
        del PENDING[k]
    token = secrets.token_hex(8)
    PENDING[token] = (str(root), now)
    return {'token': token, 'project': Path(root).name, 'where': str(root)}


def run(token):
    """The press: scan that one folder. {'name', 'text'}; PermissionError for a bad or stale token."""
    entry = PENDING.pop(token, None) if isinstance(token, str) else None
    if not entry or time.time() - entry[1] > TTL:
        raise PermissionError('token')
    root = entry[0]
    if not os.path.isdir(root):
        raise OSError('folder')
    return {'name': os.path.basename(root), 'text': scan(root)}
