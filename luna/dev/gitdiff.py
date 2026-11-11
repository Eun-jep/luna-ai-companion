"""Her hands, part 8: review of git changes, measured by the program.
She asks for it ([diff:working|staged|last|<branch>]); the creator presses; the program itself runs read-only git in the project of the file she was
last shown (no shell, no pager, no external diff tools), parses the diff and reports what changed and what looks wrong in the ADDED lines: secrets
(never printed), risky calls, forgotten debugging, merge-conflict markers, tests disabled or deleted, source changes without tests, manifest/lockfile
mismatches, migrations, infrastructure files, oversized changes. The diff text follows, riskiest files first, with secrets masked and lockfiles,
minified and secret files left without a body. Nothing is changed in the repository."""
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path

from luna.dev import codescan
from luna.dev import devtools
from luna.hands import runner

TTL, TIMEOUT, MAX_DIFF, MAX_BODY = 120, 25, 600000, 9000
PENDING = {}
REF = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/-]{0,59}$')
SCOPES = {'working': ['diff', 'HEAD'], 'staged': ['diff', '--cached'], 'last': ['show', '--format=', 'HEAD']}
LOCKS = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock', 'pipfile.lock', 'uv.lock', 'cargo.lock', 'go.sum', 'gemfile.lock', 'composer.lock', 'packages.lock.json'}
MANIFESTS = {'package.json': {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml'}, 'pyproject.toml': {'poetry.lock', 'uv.lock'}, 'pipfile': {'pipfile.lock'},
             'cargo.toml': {'cargo.lock'}, 'go.mod': {'go.sum'}, 'composer.json': {'composer.lock'}}
GENERATED = re.compile(r'(\.min\.(js|css)$|(^|/)(dist|build|out|vendor|node_modules)/|\.map$|\.snap$)', re.I)
TEST_PATH = re.compile(r'(^|/)(tests?|__tests__|spec|fixtures?)/|(^|/)test_[^/]+$|[_.](test|spec)\.\w+$', re.I)
INFRA = re.compile(r'(^|/)(dockerfile[^/]*|docker-compose[^/]*|compose\.ya?ml|\.github/workflows/[^/]+|\.gitlab-ci\.yml|jenkinsfile|[^/]+\.tf|[^/]+\.ya?ml)$', re.I)
MIGRATION = re.compile(r'(^|/)(migrations?|alembic/versions|db/migrate)/|\.sql$', re.I)
DEBUG = re.compile(r'\bbreakpoint\(\)|\bpdb\.set_trace|^\s*import pdb\b|^\s*debugger;?\s*$|\bconsole\.(log|debug)\(|System\.out\.println|\bDebug\.Log\(|\bvar_dump\(|\bConsole\.WriteLine\(|\bfmt\.Println\(')
DISABLED = re.compile(r'\b(?:it|describe|test)\.(?:only|skip)\(|\bx(?:it|describe)\(|@pytest\.mark\.(?:skip|xfail)|@unittest\.skip|@Ignore\b|@Disabled\b|\[Ignore\]|\bt\.Skip\(')
TEST_DEF = re.compile(r'^\s*(?:def test_\w+|(?:it|test)\(\s*["\']|@Test\b|\[Test\]|\[Fact\]|func Test\w+)')
CONFLICT = re.compile(r'^(?:<{7}(?: |$)|>{7}(?: |$)|={7}$)')


def parse(text):
    """Unified diff text -> [{'path','old','status','binary','add','del','lines': [(newline, '+'|'-'|' ', text)], 'mode'}]."""
    files, cur, new_no = [], None, 0
    for raw in text.split('\n'):
        if raw.startswith('diff --git '):
            m = re.match(r'diff --git a/(.+?) b/(.+)$', raw)
            cur = {'path': m.group(2) if m else raw[11:], 'old': m.group(1) if m else '', 'status': 'modified', 'binary': False, 'add': 0, 'del': 0, 'lines': [], 'mode': False}
            files.append(cur)
            new_no = 0
        elif cur is None:
            continue
        elif raw.startswith('new file mode'):
            cur['status'] = 'added'
        elif raw.startswith('deleted file mode'):
            cur['status'] = 'deleted'
        elif raw.startswith('rename to '):
            cur['status'] = 'renamed'
            cur['path'] = raw[10:]
        elif raw.startswith(('old mode', 'new mode')):
            cur['mode'] = True
        elif raw.startswith('Binary files') or raw.startswith('GIT binary patch'):
            cur['binary'] = True
        elif raw.startswith('@@'):
            m = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)', raw)
            new_no = int(m.group(1)) if m else 0
            cur['lines'].append((0, '@', raw))
        elif raw.startswith('+') and not raw.startswith('+++'):
            cur['add'] += 1
            cur['lines'].append((new_no, '+', raw[1:]))
            new_no += 1
        elif raw.startswith('-') and not raw.startswith('---'):
            cur['del'] += 1
            cur['lines'].append((0, '-', raw[1:]))
        elif raw.startswith(' '):
            cur['lines'].append((new_no, ' ', raw[1:]))
            new_no += 1
    return files


def _ext(path):
    return os.path.splitext(path.lower())[1]


def findings(files):
    """[(severity, path, line, what)] from the ADDED lines only, plus the secret list (kept apart: never printed with values)."""
    out = []
    for f in files:
        path, ext = f['path'], _ext(f['path'])
        if f['binary'] or f['status'] == 'deleted' or GENERATED.search(path) or os.path.basename(path).lower() in LOCKS:
            continue
        is_test = bool(TEST_PATH.search(path))
        for no, kind, text in f['lines']:
            if kind != '+' or len(text) > codescan.MAX_LINE:
                continue
            for name, rx in codescan.SECRETS:
                if rx.search(text):
                    out.append(('high', path, no, 'секрет в изменении: ' + name))
            m = None if is_test else codescan.ASSIGN.search(text)
            if m and not codescan.PLACEHOLDER.search(m.group(1)) and not codescan.PLACEHOLDER.search(text.split(m.group(1))[0][-30:]):
                out.append(('high', path, no, 'секрет в изменении: пароль/ключ в коде'))
            if CONFLICT.match(text):
                out.append(('high', path, no, 'остался маркер конфликта слияния'))
            for langs, sev, what, rx in codescan.RISKS:
                if ext in langs and rx.search(text):
                    out.append((sev, path, no, what))
            if DEBUG.search(text) and not is_test:
                out.append(('low', path, no, 'забытая отладка'))
            if DISABLED.search(text):
                out.append(('medium', path, no, 'тест отключён или оставлен единственным (only/skip)'))
    return out


def structure(files):
    """Notes about the shape of the whole change."""
    notes, names = [], {os.path.basename(f['path']).lower() for f in files}
    changed = sum(f['add'] + f['del'] for f in files)
    src = [f for f in files if _ext(f['path']) in codescan.LANG and not TEST_PATH.search(f['path']) and f['status'] != 'deleted' and _ext(f['path']) not in ('.html', '.css')]
    tests = [f for f in files if TEST_PATH.search(f['path'])]
    if changed > 800:
        notes.append('очень большое изменение (%d строк): такое трудно проверить, лучше разбить на части' % changed)
    elif len(files) > 25:
        notes.append('много файлов (%d): проверь, что всё относится к одной цели' % len(files))
    if sum(f['add'] for f in src) >= 30 and not tests:
        notes.append('исходный код изменён (%d новых строк), а тестов в изменении нет' % sum(f['add'] for f in src))
    gone = sum(1 for f in tests for _, k, t in f['lines'] if k == '-' and TEST_DEF.match(t))
    came = sum(1 for f in tests for _, k, t in f['lines'] if k == '+' and TEST_DEF.match(t))
    if gone > came:
        notes.append('тестов удалено больше, чем добавлено: -%d, +%d' % (gone, came))
    for mf, locks in MANIFESTS.items():
        if mf in names and not names & locks:
            notes.append('изменён %s, а lock-файл нет: зависимости могут разойтись' % mf)
    for lock in sorted(names & LOCKS):
        if not any(m in names for m, ls in MANIFESTS.items() if lock in ls) and lock not in ('go.sum',):
            notes.append('изменился %s без изменения манифеста: проверь, что это намеренно' % lock)
    if any(f['path'].lower().endswith('requirements.txt') for f in files):
        notes.append('менялись зависимости Python: проверь версии и запусти pip-audit, если он есть')
    for f in files:
        if MIGRATION.search(f['path']) and f['status'] in ('added', 'modified'):
            notes.append('миграция БД %s: проверь откат, блокировки больших таблиц и порядок выкладки' % f['path'])
            break
    infra = [f['path'] for f in files if INFRA.search(f['path']) and not f['path'].lower().endswith(('package.json',))]
    infra = [p for p in infra if not p.lower().endswith(('.yml', '.yaml')) or 'workflows' in p or 'compose' in p.lower() or p.lower().startswith('k8s')]
    if infra:
        notes.append('затронута инфраструктура: ' + ', '.join(infra[:5]) + (' и др.' if len(infra) > 5 else '') + ' (проверь права, секреты, версии образов)')
    deleted = [f['path'] for f in files if f['status'] == 'deleted']
    if deleted:
        notes.append('удалены файлы (%d): %s' % (len(deleted), ', '.join(deleted[:6])))
    if any(f['mode'] for f in files):
        notes.append('менялись права доступа файлов (mode): проверь, что это намеренно')
    return notes


def _mask(line):
    for _, rx in codescan.SECRETS:
        line = rx.sub('[секрет]', line)
    line = codescan.ASSIGN.sub(lambda m: m.group(0).replace(m.group(1), '[секрет]'), line)
    return devtools.mask_secrets(line)


def report(files, scope, extra=''):
    """The whole text for the creator's press."""
    found = findings(files)
    order = {'high': 0, 'medium': 1, 'low': 2}
    found.sort(key=lambda r: (order[r[0]], r[1], r[2]))
    adds, dels = sum(f['add'] for f in files), sum(f['del'] for f in files)
    out = ['РАЗБОР ИЗМЕНЕНИЙ (%s; посчитан программой: файлов %d, +%d −%d; секреты показаны только местом).' % (scope, len(files), adds, dels)]
    if extra:
        out.append(extra)
    top = sorted(files, key=lambda f: -(f['add'] + f['del']))[:15]
    names = {'added': 'новый', 'deleted': 'удалён', 'renamed': 'переименован', 'modified': 'изменён'}
    out.append('Файлы (по объёму): ' + '; '.join('%s [%s%s] +%d −%d' % (f['path'], names[f['status']], ', бинарный' if f['binary'] else '', f['add'], f['del']) for f in top)
               + (' и ещё %d' % (len(files) - 15) if len(files) > 15 else ''))
    if found:
        out.append('НАХОДКИ в добавленных строках (%d: высоких %d, средних %d, низких %d):' % (len(found), *(sum(r[0] == s for r in found) for s in ('high', 'medium', 'low'))))
        out += ['- [%s] %s:%d, %s' % r for r in found[:25]]
        if len(found) > 25:
            out.append('- и ещё %d' % (len(found) - 25))
    else:
        out.append('В добавленных строках не найдено секретов, опасных вызовов, забытой отладки и отключённых тестов.')
    notes = structure(files)
    if notes:
        out.append('Замечания по форме изменения:\n' + '\n'.join('- ' + n for n in notes))
    risky = {r[1] for r in found if r[0] in ('high', 'medium')}
    body, size = [], 0
    for f in sorted(files, key=lambda f: (f['path'] not in risky, -(f['add'] + f['del']))):
        base = os.path.basename(f['path']).lower()
        if f['binary'] or GENERATED.search(f['path']) or base in LOCKS or devtools.SECRET_RE.search(base) and _ext(base) not in codescan.LANG:
            body.append('### %s: без тела (бинарный, служебный или секретный файл)' % f['path'])
            continue
        chunk = ['### %s' % f['path']]
        for no, kind, text in f['lines']:
            chunk.append(text if kind == '@' else kind + _mask(text)[:300])
        piece = '\n'.join(chunk)
        if size + len(piece) > MAX_BODY:
            body.append('### %s: не поместился (смотри через git на своей стороне или покажи файл)' % f['path'])
            continue
        body.append(piece)
        size += len(piece)
    out.append('ДИФФ (опасные файлы первыми, секреты скрыты):\n' + '\n'.join(body))
    return '\n'.join(out)


# ---- running git, read-only ----

def _git(args, cwd):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0', LC_ALL='C.UTF-8')
    cmd = ['git', '--no-pager', '-c', 'core.quotepath=off', '-c', 'core.fsmonitor=false'] + args
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=TIMEOUT, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('failed') from exc
    except OSError as exc:
        raise RuntimeError('nogit') from exc
    return proc.returncode, proc.stdout[:MAX_DIFF * 2].decode('utf-8', errors='replace'), proc.stderr.decode('utf-8', errors='replace')


def scope_args(arg):
    """'' / 'working' / 'staged' / 'last' / 'main' or 'branch main' -> (key, git args, label) or None when it is not valid."""
    word = ' '.join(str(arg).split()).lower()
    if word.startswith('branch '):
        word = word[7:]
    if word in ('', 'working', 'work', 'all'):
        return 'working', SCOPES['working'], 'рабочие изменения (всё, что отличается от последнего коммита)'
    if word in ('staged', 'cached', 'index'):
        return 'staged', SCOPES['staged'], 'проиндексированные изменения (staged)'
    if word in ('last', 'head'):
        return 'last', SCOPES['last'], 'последний коммит'
    ref = str(arg).split()[-1] if str(arg).split() else ''
    if REF.match(ref) and '..' not in ref and not ref.endswith(('.', '/', '.lock')):
        return 'branch', ['diff', ref + '...HEAD', '--'], 'изменения этой ветки относительно %s' % ref
    return None


def propose(arg=''):
    """A plate: {'token','project','scope'}; {'fail': code}; None when the request is not valid."""
    sc = scope_args(arg)
    if not sc:
        return None
    if not shutil.which('git'):
        return {'fail': 'nogit'}
    root = runner.project_dir()
    if not root:
        return {'fail': 'noproject'}
    now = time.time()
    for k in [k for k, v in PENDING.items() if now - v[2] > TTL]:
        del PENDING[k]
    token = secrets.token_hex(8)
    PENDING[token] = (str(root), sc, now)
    return {'token': token, 'project': Path(root).name, 'scope': sc[2]}


def run(token, git=None):
    """The press: read-only git on that folder. {'name','text'}; PermissionError (bad token); RuntimeError(code) for 'norepo', 'badref', 'empty', 'nogit', 'failed'."""
    entry = PENDING.pop(token, None) if isinstance(token, str) else None
    if not entry or time.time() - entry[2] > TTL:
        raise PermissionError('token')
    root, (key, args, label), _ = entry
    git = git or _git
    code, out, _err = git(['rev-parse', '--is-inside-work-tree'], root)
    if code != 0:
        raise RuntimeError('norepo')
    extra = ''
    if key == 'branch':
        ref = args[1].split('...')[0]
        if git(['rev-parse', '--verify', '--quiet', ref + '^{commit}'], root)[0] != 0:
            raise RuntimeError('badref')
    if key == 'working':
        code, out, _err = git(['diff', 'HEAD', '--no-ext-diff', '--no-textconv', '--no-color'], root)
        if code != 0:   # a repository with no commits yet
            code, out, _err = git(['diff', '--no-ext-diff', '--no-textconv', '--no-color'], root)
        code2, status, _e = git(['status', '--porcelain'], root)
        fresh = sum(1 for l in status.splitlines() if l.startswith('??')) if code2 == 0 else 0
        if fresh:
            extra = 'Неотслеживаемых новых файлов: %d (git diff их не показывает, пока они не добавлены).' % fresh
    else:
        code, out, _err = git(args[:1] + ['--no-ext-diff', '--no-textconv', '--no-color'] + args[1:], root)
        if key == 'last':
            c2, subject, _e = git(['log', '-1', '--format=%h %s'], root)
            if c2 == 0:
                extra = 'Коммит: ' + _mask(subject.strip()[:120])
    if code != 0:
        raise RuntimeError('failed')
    files = parse(out[:MAX_DIFF])
    if not files:
        raise RuntimeError('empty')
    cut = ' Дифф длиннее %d КБ: разобрана только его часть.' % (MAX_DIFF // 1000) if len(out) > MAX_DIFF else ''
    return {'name': Path(root).name, 'text': report(files, label, (extra + cut).strip())}
