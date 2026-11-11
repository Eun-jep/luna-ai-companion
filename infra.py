"""Configuration and infrastructure files, checked by the program: Kubernetes manifests, Terraform, nginx, SQL migrations.
lint(path, text) -> [(severity, line, what)]. No YAML or HCL library: line and block rules for the mistakes that really hurt (containers as root or
privileged, no limits or probes, floating image tags, world-open firewalls and buckets, wildcard IAM, weak TLS, off-by-slash alias, data-losing or
table-locking migrations). Used by the project audit and when she is shown such a file; every finding is a place to look at, not a verdict."""
import os
import re

WORKLOADS = {'Deployment', 'StatefulSet', 'DaemonSet', 'ReplicaSet', 'Job', 'CronJob', 'Pod'}
SQL_COMMENT = re.compile(r'--[^\n]*|/\*.*?\*/', re.S)


def kind_of(path, text):
    ext = os.path.splitext(path.lower())[1]
    if ext == '.tf':
        return 'terraform'
    if ext == '.sql':
        return 'sql'
    if ext == '.conf' and re.search(r'(?m)^\s*(server|location|http|events)\b[^;]*\{', text):
        return 'nginx'
    if ext in ('.yml', '.yaml') and re.search(r'(?m)^apiVersion:', text) and re.search(r'(?m)^kind:', text):
        return 'k8s'
    return ''


def _k8s(text):
    out = []
    docs, start, buf = [], 1, []
    for i, line in enumerate(text.split('\n'), 1):
        if re.match(r'^---\s*$', line):
            docs.append((start, '\n'.join(buf)))
            start, buf = i + 1, []
        else:
            buf.append(line)
    docs.append((start, '\n'.join(buf)))
    for first, doc in docs:
        k = re.search(r'(?m)^kind:\s*(\w+)', doc)
        if not k:
            continue
        kind = k.group(1)
        name = re.search(r'(?m)^metadata:\s*\n(?:[ \t]+.*\n)*?[ \t]+name:\s*"?([\w.-]+)', doc)
        label = '%s %s: ' % (kind, name.group(1)) if name else kind + ': '
        lines = doc.split('\n')

        def at(rx, sev, what, flags=0):
            for j, l in enumerate(lines):
                if re.search(rx, l, flags):
                    out.append((sev, first + j, label + what))
        if kind in WORKLOADS:
            for j, l in enumerate(lines):
                m = re.match(r'^\s*-?\s*image:\s*["\']?([^\s"\']+)', l)
                if m:
                    img = m.group(1)
                    if '@sha256:' not in img and not img.startswith(('$', '{')) and (':' not in img.rsplit('/', 1)[-1] or img.endswith(':latest')):
                        out.append(('medium', first + j, label + 'образ без фиксированной версии (%s): сборки не воспроизводимы' % img[:50]))
            if not re.search(r'(?m)^\s*limits:', doc):
                out.append(('medium', first, label + 'не заданы resources.limits: один под может съесть всю ноду'))
            if kind in ('Deployment', 'StatefulSet', 'DaemonSet') and not re.search(r'(?m)^\s*(readinessProbe|livenessProbe|startupProbe):', doc):
                out.append(('medium', first, label + 'нет readiness/liveness-проб: трафик пойдёт в под, который ещё не готов или завис'))
            if re.search(r'(?m)^\s*image:', doc) and not re.search(r'(?m)^\s*runAsNonRoot:\s*true|^\s*runAsUser:\s*[1-9]', doc):
                out.append(('low', first, label + 'не задан runAsNonRoot: контейнер может работать от root'))
            if kind == 'Deployment' and re.search(r'(?m)^\s*replicas:\s*1\s*$', doc):
                out.append(('low', first, label + 'одна реплика: при перезапуске ноды сервис недоступен'))
            at(r'^\s*privileged:\s*true', 'high', 'привилегированный контейнер (почти полный доступ к ноде)')
            at(r'^\s*(hostNetwork|hostPID|hostIPC):\s*true', 'high', 'доступ к сети или процессам ноды (hostNetwork/hostPID/hostIPC)')
            at(r'^\s*allowPrivilegeEscalation:\s*true', 'high', 'allowPrivilegeEscalation: true')
            at(r'^\s*runAsUser:\s*0\s*$', 'high', 'запуск от root (runAsUser: 0)')
            at(r'^\s*hostPath:', 'medium', 'hostPath: том с файловой системой ноды')
            at(r'^\s*-\s*(SYS_ADMIN|ALL|NET_ADMIN|SYS_PTRACE)\b', 'high', 'опасная capability у контейнера')
            at(r'^\s*(value|-\s*value):\s*["\']?[^\s"\']{8,}', 'low', 'значение прямо в env: секреты клади в Secret и бери через secretKeyRef') if re.search(r'(?i)(password|token|secret|key)\w*', doc) and re.search(r'(?m)^\s*-?\s*name:\s*\S*(PASSWORD|TOKEN|SECRET|KEY)', doc) else None
        elif kind == 'Secret' and re.search(r'(?m)^(data|stringData):\s*\n\s+\S', doc):
            out.append(('medium', first, label + 'Secret с данными лежит в репозитории (base64 не шифрование): используй sealed-secrets, SOPS или внешний менеджер секретов'))
        elif kind == 'Ingress' and not re.search(r'(?m)^\s*tls:', doc):
            out.append(('medium', first, label + 'Ingress без tls: трафик пойдёт без шифрования'))
        elif kind == 'Service' and re.search(r'(?m)^\s*type:\s*(LoadBalancer|NodePort)', doc):
            out.append(('low', first, label + 'сервис открыт наружу (LoadBalancer/NodePort): проверь, что так и задумано'))
        elif kind in ('ClusterRoleBinding', 'RoleBinding') and re.search(r'(?m)^\s*name:\s*cluster-admin\b', doc):
            out.append(('high', first, label + 'привязка к cluster-admin: полный доступ ко всему кластеру'))
        elif kind in ('ClusterRole', 'Role') and re.search(r'(?m)^\s*(verbs|resources):\s*\[?\s*["\']?\*', doc):
            out.append(('high', first, label + 'роль с «*» в verbs или resources: слишком широкие права'))
        if re.search(r'(?m)^\s*namespace:\s*default\s*$', doc):
            out.append(('low', first, label + 'namespace default: выдели свой неймспейс'))
    return out


def _terraform(text):
    out, lines = [], text.split('\n')
    for i, l in enumerate(lines):
        n = i + 1
        a = i
        while a > 0 and not lines[a].rstrip().endswith('{'):
            a -= 1
        b = i
        while b < len(lines) - 1 and not lines[b].strip().startswith('}'):
            b += 1
        near = '\n'.join(lines[a:b + 1])
        if re.search(r'["\']0\.0\.0\.0/0["\']|["\']::/0["\']', l):
            risky = re.search(r'(from_port|to_port)\s*=\s*(22|3389|3306|5432|1433|6379|27017|9200)\b', near)
            out.append(('high' if risky else 'medium', n, 'Terraform: доступ отовсюду (0.0.0.0/0)' + (' к чувствительному порту (SSH, RDP, база)' if risky else '')))
        if re.search(r'\bacl\s*=\s*["\']public-read(-write)?["\']', l):
            out.append(('high', n, 'Terraform: бакет открыт на публичное чтение или запись'))
        if re.search(r'\bpublicly_accessible\s*=\s*true', l):
            out.append(('high', n, 'Terraform: база доступна из интернета (publicly_accessible)'))
        if re.search(r'\b(storage_encrypted|encrypted)\s*=\s*false', l):
            out.append(('medium', n, 'Terraform: шифрование диска или хранилища выключено'))
        if re.search(r'\bskip_final_snapshot\s*=\s*true|\bdeletion_protection\s*=\s*false', l):
            out.append(('low', n, 'Terraform: ресурс удаляется без финального снимка или защиты от удаления'))
        if re.search(r'["\'](Action|Resource)["\']?\s*[:=]\s*["\']\*["\']|\bactions\s*=\s*\[\s*["\']\*["\']|\bresources\s*=\s*\[\s*["\']\*["\']', l):
            out.append(('high', n, 'Terraform: IAM-политика со звёздочкой в Action или Resource (слишком широкие права)'))
        if re.search(r'\b(access_key|secret_key|password|token)\s*=\s*"(?!\$\{|var\.)[^"\s]{6,}"', l, re.I):
            out.append(('high', n, 'Terraform: секрет прямо в коде (используй переменные и менеджер секретов)'))
    if re.search(r'(?m)^\s*provider\s+"', text) and not re.search(r'required_providers|version\s*=', text):
        out.append(('low', 1, 'Terraform: версии провайдеров не зафиксированы (required_providers)'))
    return out


def _nginx(text):
    out, lines = [], text.split('\n')
    for i, l in enumerate(lines):
        n = i + 1
        s = l.split('#', 1)[0]
        if re.search(r'\bautoindex\s+on\b', s):
            out.append(('medium', n, 'nginx: autoindex on показывает список файлов каталога'))
        if re.search(r'\bssl_protocols\b[^;]*\b(SSLv3|TLSv1|TLSv1\.1)\b(?!\.)', s) and not re.search(r'\bssl_protocols\s+TLSv1\.[23]', s):
            out.append(('high', n, 'nginx: разрешены устаревшие протоколы TLS (SSLv3, TLS 1.0 или 1.1)'))
        elif re.search(r'\bssl_protocols\b[^;]*\b(SSLv3|TLSv1)\b(?![.\d])', s):
            out.append(('high', n, 'nginx: разрешены устаревшие протоколы TLS (SSLv3 или TLS 1.0)'))
        if re.search(r'Access-Control-Allow-Origin\s+["\']?\*', s):
            out.append(('medium', n, 'nginx: CORS открыт всем (Access-Control-Allow-Origin *)'))
        if re.search(r'\bserver_tokens\s+on\b', s):
            out.append(('low', n, 'nginx: server_tokens on раскрывает версию сервера'))
        m = re.match(r'\s*location\s+(?:[~^=*]+\s+)?(/\S*)\s*\{', s)
        if m:
            loc = m.group(1)
            for j in range(i + 1, min(i + 8, len(lines))):
                a = re.match(r'\s*alias\s+(\S+);', lines[j].split('#', 1)[0])
                if a:
                    if not loc.endswith('/') and a.group(1).endswith('/') and not m.group(0).lstrip().startswith(('location ~', 'location =')):
                        out.append(('medium', j + 1, 'nginx: location %s без слеша в конце, а alias со слешем: выход из каталога через /%s../' % (loc, loc.strip('/'))))
                    break
                if '}' in lines[j]:
                    break
        if re.match(r'\s*if\s*\(', s):
            out.append(('low', n, 'nginx: if внутри location ведёт себя неочевидно («if is evil»), лучше map или try_files'))
    return out


def _sql(text):
    out = []
    clean = SQL_COMMENT.sub(lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text)   # keeps line numbers
    pos = 0
    for stmt in clean.split(';'):
        line = clean.count('\n', 0, pos) + 1 + (len(stmt) - len(stmt.lstrip('\n \t\r')) and stmt[:len(stmt) - len(stmt.lstrip())].count('\n'))
        pos += len(stmt) + 1
        s = ' '.join(stmt.split())
        if not s:
            continue
        up = s.upper()
        if re.match(r'(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE)\b', up) or re.search(r'\bDROP\s+COLUMN\b', up):
            out.append(('high', line, 'SQL: удаляет данные безвозвратно (' + s[:50] + '): нужен откат и резервная копия'))
        if re.match(r'(DELETE\s+FROM|UPDATE)\b', up) and ' WHERE ' not in up + ' ':
            out.append(('high', line, 'SQL: ' + up.split()[0] + ' без WHERE затронет все строки таблицы'))
        if re.search(r'\bALTER\s+TABLE\b.*\bADD\s+(COLUMN\s+)?\S+\s+[^,]*\bNOT\s+NULL\b', up) and 'DEFAULT' not in up:
            out.append(('medium', line, 'SQL: новая колонка NOT NULL без DEFAULT: упадёт или надолго заблокирует непустую таблицу'))
        if re.search(r'\bALTER\s+TABLE\b.*\bALTER\s+COLUMN\b.*\b(TYPE|SET\s+DATA\s+TYPE)\b|\bMODIFY\s+COLUMN\b', up):
            out.append(('medium', line, 'SQL: смена типа колонки перезаписывает таблицу и блокирует её на время выполнения'))
        if re.search(r'\bRENAME\s+(COLUMN|TO)\b|\bRENAME\s+TABLE\b', up):
            out.append(('medium', line, 'SQL: переименование ломает старую версию кода во время выкладки: делай в два шага'))
        if re.match(r'CREATE\s+(UNIQUE\s+)?INDEX\b', up) and 'CONCURRENTLY' not in up:
            out.append(('low', line, 'SQL: индекс строится с блокировкой записи (в PostgreSQL используй CONCURRENTLY, в MySQL проверь ALGORITHM=INPLACE)'))
        if re.match(r'GRANT\s+ALL\b', up):
            out.append(('medium', line, 'SQL: GRANT ALL выдаёт лишние права: дай только нужные'))
    return out


def lint(path, text):
    """[(severity, line, what)] sorted by line, [] when the file is not a recognised config."""
    kind = kind_of(path, text)
    found = {'k8s': _k8s, 'terraform': _terraform, 'nginx': _nginx, 'sql': _sql}.get(kind, lambda t: [])(text)
    return sorted({f for f in found if f}, key=lambda f: (f[1], f[0]))


def summary(path, text, limit=12):
    """A short block for the end of a file she is shown, '' when nothing was found or it is not a config."""
    found = lint(path, text)
    if not found:
        return ''
    order = {'high': 0, 'medium': 1, 'low': 2}
    found.sort(key=lambda f: (order[f[0]], f[1]))
    rows = ['- [%s] строка %d: %s' % f for f in found[:limit]]
    if len(found) > limit:
        rows.append('- и ещё %d' % (len(found) - limit))
    return 'ПРОВЕРКА ПРОГРАММЫ (правила для конфигов; это места, куда стоит посмотреть, а не приговор):\n' + '\n'.join(rows)
