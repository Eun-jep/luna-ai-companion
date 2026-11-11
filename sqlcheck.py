"""SQL in his message, read by the program before she answers.
She does not run anything on a database: the program only splits the statements, says what each one does (read, write, schema, dangerous) and flags
the mistakes that really hurt: DELETE/UPDATE without WHERE, DROP/TRUNCATE, `= NULL`, SELECT * on a join, a join with no condition, a function on a
column in WHERE (the index is lost), a leading % in LIKE, NOT IN with a subquery, string-glued values (injection), no LIMIT on an open SELECT.
No SQL library: line and token rules, comments and string literals are blanked first so they never trigger a rule."""
import re

MAX_REPORT = 2200

KEYWORDS = re.compile(r'(?is)^\s*(select|with|insert|update|delete|merge|replace|create|alter|drop|truncate|grant|revoke|explain|pragma|show|describe|call|exec|execute)\b')

STARTS = re.compile(r'(?i)\bselect\b.+\bfrom\b|\binsert\s+into\b|\bupdate\s+[\w."`\[\]]+\s+set\b|\bdelete\s+from\b|\b(?:drop|truncate|alter)\s+(?:table|index|database|schema)\b|\bcreate\s+(?:unique\s+)?(?:table|index)\b|\bwith\s+\w+\s+as\s*\(')


def blank(sql):
    """Comments and string contents replaced by spaces / empty quotes, so that rules only see real SQL."""
    sql = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.S)
    sql = re.sub(r'--[^\n]*', ' ', sql)
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    return sql


def statements(text):
    out = []
    for part in blank(text).split(';'):
        part = ' '.join(part.split())
        if not KEYWORDS.match(part):   # prose in front of the statement: cut from where the statement really starts
            m = STARTS.search(part)
            part = part[m.start():] if m else ''
        if KEYWORDS.match(part):
            out.append(part)
    return out


def looks_like_sql(text):
    if not isinstance(text, str) or len(text) < 12:
        return False
    return bool(re.search(r'(?is)\bselect\b.+\bfrom\b|\binsert\s+into\b|\bupdate\b\s+[\w."`\[\]]+\s+set\b|\bdelete\s+from\b|\b(?:drop|truncate|alter)\s+table\b|\bcreate\s+(?:unique\s+)?(?:table|index)\b', blank(text)))


def kind(stmt):
    word = KEYWORDS.match(stmt).group(1).lower()
    if word in ('select', 'explain', 'show', 'describe', 'pragma'):
        return 'чтение'
    if word == 'with':
        return 'запись' if re.search(r'(?i)\b(insert|update|delete)\b', stmt) else 'чтение'
    if word in ('insert', 'update', 'delete', 'merge', 'replace'):
        return 'запись'
    if word in ('create', 'alter', 'drop', 'truncate'):
        return 'схема'
    return 'прочее'


def check(stmt):
    """-> [(level, what)] with level 'опасно' or 'внимание'."""
    s = stmt
    low = s.lower()
    out = []
    head = KEYWORDS.match(s).group(1).lower()
    has_where = bool(re.search(r'(?i)\bwhere\b', s))
    if head in ('delete', 'update') and not has_where:
        out.append(('опасно', '%s без WHERE затронет ВСЕ строки таблицы. Сначала SELECT count(*) с тем же условием, и транзакция с откатом' % head.upper()))
    if head in ('drop', 'truncate'):
        out.append(('опасно', '%s стирает данные или таблицу без отката во многих СУБД: нужна резервная копия и уверенность, что это та база' % head.upper()))
    if head == 'alter' and re.search(r'(?i)\bdrop\s+(column|constraint|primary)', s):
        out.append(('опасно', 'ALTER … DROP удаляет колонку или ограничение вместе с данными: проверь зависимости и копию'))
    if re.search(r'(?i)(=|<>|!=)\s*null(?!\w)', s):
        out.append(('внимание', 'сравнение с NULL через = или <> никогда не истинно: нужно IS NULL / IS NOT NULL'))
    if head in ('select', 'with'):
        if re.search(r'(?i)select\s+(distinct\s+)?\*', s) and re.search(r'(?i)\bjoin\b', s):
            out.append(('внимание', 'SELECT * при JOIN: одинаковые имена колонок затрут друг друга и лишнее тянется по сети; перечисли нужные колонки'))
        if re.search(r'(?i)\bfrom\s+\w[\w.]*\s*,\s*\w', s) and not has_where:
            out.append(('опасно', 'таблицы через запятую без WHERE: получится декартово произведение (строк станет a×b)'))
        if re.search(r'(?i)\bjoin\b', s) and not re.search(r'(?i)\b(on|using)\b', s) and not re.search(r'(?i)\bcross\s+join\b|\bnatural\s+join\b', s):
            out.append(('опасно', 'JOIN без ON/USING: декартово произведение'))
        if re.search(r"(?i)\blike\s+'%", s):
            out.append(('внимание', "LIKE '%…' с процентом в начале не использует индекс: на большой таблице полный перебор"))
        if re.search(r'(?i)\bwhere\b.*\b(lower|upper|date|year|month|substr(ing)?|cast|coalesce|trim)\s*\(\s*[a-z_][\w.]*\s*\)\s*(=|<|>|like|in)', s):
            out.append(('внимание', 'функция над колонкой в WHERE: индекс по этой колонке не сработает; сравнивай колонку как есть (диапазон дат вместо date(col))'))
        if re.search(r'(?i)\bnot\s+in\s*\(\s*select\b', s):
            out.append(('внимание', 'NOT IN с подзапросом: одно NULL в подзапросе обнулит весь результат; лучше NOT EXISTS'))
        if not re.search(r'(?i)\blimit\b|\btop\b|\bfetch\s+first\b|\bcount\s*\(|\bgroup\s+by\b|\bwhere\b', s) and head == 'select':
            out.append(('внимание', 'SELECT без WHERE и LIMIT на большой таблице вернёт всё: добавь LIMIT, пока смотришь данные'))
        if re.search(r'(?i)\border\s+by\s+rand(om)?\s*\(', s):
            out.append(('внимание', 'ORDER BY RANDOM() сортирует всю таблицу: на больших таблицах очень медленно'))
    if re.search(r"(?:\+|\|\|)\s*\$?\w+\s*(?:\+|\|\|)\s*''|'\s*(?:\+|\|\|)\s*\w+|\bformat\s*\(|%s'|\{\w+\}'", s):
        out.append(('внимание', 'значение склеено в строку запроса: это дыра для SQL-инъекции; используй параметры (?, $1, :name), а не склейку'))
    if head == 'insert' and not re.search(r'(?i)insert\s+(or\s+\w+\s+)?into\s+[\w."`]+\s*\(', s) and re.search(r'(?i)\bvalues\b', s):
        out.append(('внимание', 'INSERT без списка колонок ломается, когда в таблице добавят колонку; перечисли колонки'))
    return out


def analyze(text):
    """The short reading of the SQL in a message; '' when there is none."""
    if not looks_like_sql(text):
        return ''
    stmts = statements(text)[:6]
    if not stmts:
        return ''
    out = ['Разбор SQL программой (она ничего не выполняла и к базе не подключалась; опирайся на разбор: скажи, что делает запрос, чем рискован, '
           'и предложи безопасный порядок, например сначала SELECT с тем же условием; выполнять запросы на его базе она не будет).']
    dangerous = False
    for n, st in enumerate(stmts, 1):
        marks = check(st)
        dangerous = dangerous or any(m[0] == 'опасно' for m in marks)
        line = '%d) %s: %s' % (n, kind(st), st[:110] + ('…' if len(st) > 110 else ''))
        if marks:
            line += ' — ' + '; '.join('%s: %s' % m for m in marks[:3])
        out.append(line)
    if len(statements(text)) > len(stmts):
        out.append('Запросов больше, разобраны первые %d.' % len(stmts))
    if dangerous:
        out.append('Есть опасное: предупреди об этом ПЕРВЫМ делом, до объяснений. Запись и удаление на боевой базе только после копии и проверки условием.')
    return '\n'.join(out)[:MAX_REPORT]
