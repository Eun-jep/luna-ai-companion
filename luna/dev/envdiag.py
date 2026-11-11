"""Diagnostics of this computer for "why does it not start here": who holds a port, how much disk and memory is left, which developer tools
are installed in which version and which of them the open project needs. Everything is read-only and fixed: a short list of commands
without arguments from outside, nothing is stopped, changed or installed; to free a port she only tells how."""
import ctypes
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path

from luna.hands import runner

TTL, TIMEOUT = 120, 8
PENDING = {}
ARG = re.compile(r'^(all|ports|disk|tools|(?:port[\s:]*)?\d{1,5})$', re.I)
TOOLS = [('python', ['python', '--version']), ('pip', ['pip', '--version']), ('node', ['node', '--version']), ('npm', ['npm', '--version']),
         ('git', ['git', '--version']), ('docker', ['docker', '--version']), ('java', ['java', '-version']), ('dotnet', ['dotnet', '--version']),
         ('go', ['go', 'version']), ('rustc', ['rustc', '--version']), ('cargo', ['cargo', '--version']), ('kubectl', ['kubectl', 'version', '--client']),
         ('terraform', ['terraform', '--version']), ('make', ['make', '--version']), ('cmake', ['cmake', '--version'])]
NEEDS = [('package.json', 'node'), ('requirements.txt', 'python'), ('pyproject.toml', 'python'), ('setup.py', 'python'), ('go.mod', 'go'),
         ('Cargo.toml', 'cargo'), ('pom.xml', 'java'), ('build.gradle', 'java'), ('Dockerfile', 'docker'), ('docker-compose.yml', 'docker'),
         ('docker-compose.yaml', 'docker'), ('compose.yml', 'docker'), ('CMakeLists.txt', 'cmake'), ('Makefile', 'make')]
PORTS = {80: 'HTTP (веб-сервер)', 443: 'HTTPS', 3000: 'dev-сервер Node/React', 3306: 'MySQL', 4200: 'Angular dev', 5000: 'Flask/сервисы .NET',
         5173: 'Vite dev', 5432: 'PostgreSQL', 5672: 'RabbitMQ', 6379: 'Redis', 8000: 'Django/FastAPI dev', 8080: 'альтернативный HTTP (Tomcat, прокси, dev)',
         8888: 'Jupyter', 9000: 'PHP-FPM/SonarQube/прочее', 9200: 'Elasticsearch', 27017: 'MongoDB', 1433: 'SQL Server', 2375: 'Docker API без TLS (опасно)'}


def scope_of(arg):
    """('all'|'ports'|'disk'|'tools'|'port', number) or None when the request is not one of these."""
    a = ' '.join(str(arg or 'all').lower().split()) or 'all'
    if not ARG.match(a):
        return None
    if a.isalpha():
        return a, 0
    n = int(re.sub(r'\D', '', a))
    return ('port', n) if 0 < n < 65536 else None


def _sh(args, timeout=TIMEOUT):
    """(code, stdout+stderr) of a fixed command; (-1, '') when it is missing, hangs or fails to start."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, errors='replace', timeout=timeout, stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or '') + (p.stderr or '')
    except (OSError, subprocess.SubprocessError):
        return -1, ''


def parse_netstat(text):
    """Listening TCP sockets -> [(port, pid, address)] from `netstat -ano` (Windows) or `ss -ltnp` style lines."""
    out = []
    for line in text.splitlines():
        m = re.match(r'\s*TCP\s+(\S+):(\d+)\s+\S+\s+LISTENING\s+(\d+)', line, re.I)
        if m:
            out.append((int(m.group(2)), int(m.group(3)), m.group(1).strip('[]')))
    return out


def parse_tasklist(text):
    """{pid: image name} from `tasklist /fo csv /nh`."""
    names = {}
    for line in text.splitlines():
        m = re.match(r'"([^"]*)","(\d+)"', line.strip())
        if m:
            names[int(m.group(2))] = m.group(1)
    return names


def listening():
    """[(port, pid, address, process name)] without duplicates, sorted by port."""
    if os.name != 'nt':
        return []
    code, net = _sh(['netstat', '-ano', '-p', 'tcp'])
    if code != 0:
        return []
    names = parse_tasklist(_sh(['tasklist', '/fo', 'csv', '/nh'])[1])
    seen, rows = set(), []
    for port, pid, addr in parse_netstat(net):
        if (port, pid) not in seen:
            seen.add((port, pid))
            rows.append((port, pid, addr, names.get(pid, '?')))
    return sorted(rows)


def exposed(addr):
    return addr not in ('127.0.0.1', '::1')


def disks():
    """[(drive, free bytes, total bytes)] for the drives that exist."""
    rows = []
    if os.name == 'nt':
        for letter in 'CDEFGHIJ':
            root = letter + ':\\'
            if os.path.exists(root):
                try:
                    u = shutil.disk_usage(root)
                    rows.append((letter + ':', u.free, u.total))
                except OSError:
                    pass
    else:
        u = shutil.disk_usage('/')
        rows.append(('/', u.free, u.total))
    return rows


def memory():
    """(free bytes, total bytes) of RAM, None when unknown."""
    if os.name != 'nt':
        return None

    class Status(ctypes.Structure):
        _fields_ = [('l', ctypes.c_ulong), ('load', ctypes.c_ulong), ('total', ctypes.c_ulonglong), ('free', ctypes.c_ulonglong),
                    ('pt', ctypes.c_ulonglong), ('pf', ctypes.c_ulonglong), ('vt', ctypes.c_ulonglong), ('vf', ctypes.c_ulonglong), ('ex', ctypes.c_ulonglong)]
    s = Status()
    s.l = ctypes.sizeof(Status)
    try:
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
            return s.free, s.total
    except (OSError, AttributeError):
        pass
    return None


def version_of(text):
    m = re.search(r'\d+(?:\.\d+){1,3}', text or '')
    return m.group(0) if m else ''


def tools(run=None):
    """{name: version or ''} for the tools found on PATH; a missing tool is absent from the result."""
    run = run or _sh
    found = {}
    for name, cmd in TOOLS:
        exe = shutil.which(cmd[0])
        if not exe:
            continue
        code, out = run([exe] + cmd[1:])
        found[name] = version_of(out) if code == 0 else ''
    return found


def project_needs(root):
    """Tools the open project calls for, judged by its files: {tool: [file names]}."""
    need = {}
    try:
        names = set(os.listdir(root))
    except OSError:
        return need
    for fname, tool in NEEDS:
        if fname in names:
            need.setdefault(tool, []).append(fname)
    if any(n.endswith(('.csproj', '.sln')) for n in names):
        need.setdefault('dotnet', []).append('.csproj/.sln')
    if any(n.endswith('.tf') for n in names):
        need.setdefault('terraform', []).append('*.tf')
    return need


def pinned_node(root):
    """The Node version the project asks for: (major, file) from .nvmrc / .node-version, or None."""
    for fname in ('.nvmrc', '.node-version'):
        try:
            m = re.search(r'\d+', (Path(root) / fname).read_text(encoding='utf-8', errors='replace'))
        except OSError:
            continue
        if m:
            return int(m.group(0)), fname
    return None


def _gb(n):
    return '%.1f ГБ' % (n / 1024 ** 3)


def report(scope, listen=None, drive=None, ram=None, tool_versions=None, root=None):
    """The text for her. The inputs can be replaced (tests)."""
    kind, num = scope
    out, notes = ['ДИАГНОСТИКА КОМПЬЮТЕРА (собрано программой, только чтение; ничего не остановлено и не изменено).'], []
    if kind in ('all', 'ports', 'port'):
        rows = listening() if listen is None else listen
        if kind == 'port':
            hit = [r for r in rows if r[0] == num]
            if hit:
                for port, pid, addr, name in hit:
                    out.append('Порт %d занят: процесс %s (PID %d), слушает %s%s.' % (port, name, pid, addr, ' — доступен из сети' if exposed(addr) else ' — только этот компьютер'))
                    notes.append('Освободить порт %d: закрыть %s или завершить процесс командой taskkill /PID %d (я сама ничего не завершаю; смотри, не системный ли это процесс), либо запустить свою программу на другом порту.' % (port, name, pid))
            else:
                out.append('Порт %d свободен: его никто не слушает. Если программа всё равно не стартует, дело не в этом порту (права, адрес, брандмауэр).' % num)
        else:
            out.append('Слушающие порты (%d):' % len(rows))
            for port, pid, addr, name in rows[:30]:
                hint = PORTS.get(port)
                out.append('- %d: %s (PID %d), %s%s' % (port, name, pid, 'из сети' if exposed(addr) else 'локально', ' — обычно ' + hint if hint else ''))
            if len(rows) > 30:
                out.append('- и ещё %d' % (len(rows) - 30))
            if not rows:
                out.append('- не удалось получить список (нет netstat или не Windows)')
            danger = [r for r in rows if r[0] == 2375 and exposed(r[2])]
            if danger:
                notes.append('Docker API на 2375 открыт в сеть без TLS: любой в сети получает контроль над машиной.')
    if kind in ('all', 'disk'):
        rows = disks() if drive is None else drive
        out.append('Диски:')
        for letter, free, total in rows:
            share = free / total if total else 1
            out.append('- %s свободно %s из %s (%d%%)' % (letter, _gb(free), _gb(total), round(share * 100)))
            if share < 0.08 or free < 5 * 1024 ** 3:
                notes.append('На диске %s мало места (%s): сборки, образы Docker и кэш пакетов могут падать с ошибкой записи.' % (letter, _gb(free)))
        mem = memory() if ram is None else ram
        if mem:
            out.append('Память: свободно %s из %s' % (_gb(mem[0]), _gb(mem[1])))
            if mem[0] < 1.5 * 1024 ** 3:
                notes.append('Свободной памяти мало (%s): тяжёлые сборки и контейнеры будут тормозить или падать.' % _gb(mem[0]))
    if kind in ('all', 'tools'):
        found = tools() if tool_versions is None else tool_versions
        out.append('Инструменты (из PATH): ' + (', '.join('%s %s' % (k, v or '?') for k, v in found.items()) or 'ничего не найдено'))
        r = runner.project_dir() if root is None else root
        if r:
            need = project_needs(r)
            if need:
                out.append('Проекту «%s» нужны (по файлам): %s' % (Path(r).name, ', '.join('%s (%s)' % (t, ', '.join(f)) for t, f in need.items())))
            for tool, files in need.items():
                have = 'python' if tool == 'python' and 'python' in found else tool
                if have not in found and not (tool == 'python' and 'py' in found):
                    notes.append('Не найден %s, а проекту он нужен (%s): установи его или добавь в PATH (после установки перезапусти терминал).' % (tool, ', '.join(files)))
            pin = pinned_node(r)
            if pin and found.get('node'):
                have_major = int(found['node'].split('.')[0])
                if have_major != pin[0]:
                    notes.append('Проект просит Node %d (%s), а установлен %s: версии расходятся, переключись через nvm или fnm.' % (pin[0], pin[1], found['node']))
            if 'docker' in need and 'docker' in found:
                notes.append('Docker установлен, но запущен ли демон, я не проверяла: если docker ps не отвечает, запусти Docker Desktop.')
        if 'pip' in found and 'python' not in found:
            notes.append('pip есть, а python в PATH нет: pip, скорее всего, от другой установки.')
    if notes:
        out.append('')
        out.append('На что обратить внимание:')
        out += ['- ' + n for n in notes]
    return '\n'.join(out)


def propose(arg=''):
    """A plate: {'token','scope'}; None when the request is not valid."""
    sc = scope_of(arg)
    if not sc:
        return None
    now = time.time()
    for k in [k for k, v in PENDING.items() if now - v[1] > TTL]:
        del PENDING[k]
    token = secrets.token_hex(8)
    PENDING[token] = (sc, now)
    label = {'all': 'порты, диск, память и инструменты', 'ports': 'слушающие порты', 'disk': 'диск и память', 'tools': 'установленные инструменты',
             'port': 'кто занимает порт %d' % sc[1]}[sc[0]]
    return {'token': token, 'scope': label}


def run(token):
    """The press: collect the facts. {'name','text'}; PermissionError for a bad or stale token."""
    entry = PENDING.pop(token, None) if isinstance(token, str) else None
    if not entry or time.time() - entry[1] > TTL:
        raise PermissionError('token')
    return {'name': 'компьютер', 'text': report(entry[0])}
