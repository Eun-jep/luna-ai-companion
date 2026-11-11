"""A read-only look into a SQLite file of the project, only when he presses.
She asks with [sql:query] (or [sql:file.db >> query] when the project has several databases); he sees the exact query and the file on a plate and
presses Run (single use, two minutes). One statement, and only a read: SELECT, WITH ... SELECT, EXPLAIN. The file is opened read-only
(mode=ro, query_only), the query is cut after a few seconds and the result after a few dozen rows; values of columns that look like secrets are
hidden. Other databases (PostgreSQL, MySQL) are never touched: for them she only checks the query text (sqlcheck.py)."""
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

from luna.dev import devtools
from luna.hands import runner
from luna.dev import sqlcheck

TTL = 120
MAX_ROWS = 40
MAX_CELL = 80
MAX_TEXT = 4000
SECONDS = 5
EXT = ('.db', '.sqlite', '.sqlite3', '.db3')
SECRET_COL = re.compile(r'(?i)(pass(word|wd)?|pwd|secret|token|api.?key|hash|salt|card|cvv|iban|ssn)')
FORBIDDEN = re.compile(r'(?i)(?<![\w.])(attach|detach|load_extension|pragma|vacuum|reindex|savepoint)(?![\w])')   # not a read, or reaches outside the file

PENDING = {}


def databases(root):
    """SQLite files in the project folder and one level below, nearest first."""
    found = []
    try:
        for entry in sorted(os.listdir(root)):
            p = Path(root) / entry
            if p.is_file() and entry.lower().endswith(EXT):
                found.append(p)
            elif p.is_dir() and not entry.startswith('.') and entry not in ('node_modules', '__pycache__', 'venv', '.venv'):
                try:
                    found += [p / n for n in sorted(os.listdir(p)) if n.lower().endswith(EXT) and (p / n).is_file()]
                except OSError:
                    pass
    except OSError:
        pass
    return found[:10]


def check(query):
    """-> clean single read statement, or raises ValueError('notread' | 'empty' | 'many')."""
    stmts = sqlcheck.statements(query)
    if not stmts:
        raise ValueError('empty')
    if len(stmts) > 1:
        raise ValueError('many')
    stmt = stmts[0]
    if sqlcheck.kind(stmt) != 'чтение' or FORBIDDEN.search(sqlcheck.blank(stmt)):
        raise ValueError('notread')
    return query.strip().rstrip(';').strip()[:400]


def propose(arg):
    """A plate {'token','project','db','sql'}; {'fail': code}; None for an empty request."""
    arg = str(arg or '').strip()
    if not arg:
        return None
    root = runner.project_dir()
    if not root:
        return {'fail': 'noproject'}
    wanted = ''
    if '>>' in arg:
        wanted, arg = [x.strip() for x in arg.split('>>', 1)]
    try:
        query = check(arg)
    except ValueError as exc:
        return {'fail': str(exc)}
    files = databases(root)
    if wanted:
        files = [f for f in files if f.name.lower() == wanted.lower()]
    if not files:
        return {'fail': 'nodb'}
    if len(files) > 1:
        return {'fail': 'whichdb', 'names': [f.name for f in files][:5]}
    now = time.time()
    for k in [k for k, v in PENDING.items() if now - v[2] > TTL]:
        del PENDING[k]
    token = secrets.token_hex(8)
    PENDING[token] = (str(files[0]), query, now)
    return {'token': token, 'project': Path(root).name, 'db': files[0].name, 'sql': query}


def _cell(name, value):
    if value is None:
        return 'NULL'
    if SECRET_COL.search(name or ''):
        return '***'
    if isinstance(value, bytes):
        return '<%d байт>' % len(value)
    text = devtools.mask_secrets(str(value)).replace('\n', ' ')
    return text if len(text) <= MAX_CELL else text[:MAX_CELL] + '…'


def run(token):
    """The press. {'name','db','text','rows','cut'}; PermissionError (bad token); RuntimeError('badquery' | 'timeout' | 'failed')."""
    entry = PENDING.pop(token, None) if isinstance(token, str) else None
    if not entry or time.time() - entry[2] > TTL:
        raise PermissionError('token')
    path, query, _ = entry
    try:
        con = sqlite3.connect('file:%s?mode=ro' % Path(path).as_posix().replace('?', '%3f'), uri=True, timeout=2)
    except sqlite3.Error:
        raise RuntimeError('failed')
    try:
        con.execute('PRAGMA query_only = ON')
        started = time.time()
        con.set_progress_handler(lambda: 1 if time.time() - started > SECONDS else 0, 20000)
        try:
            cur = con.execute(query)
            rows = cur.fetchmany(MAX_ROWS + 1)
        except sqlite3.OperationalError as exc:
            raise RuntimeError('timeout' if 'interrupt' in str(exc).lower() else 'badquery:' + devtools.mask_secrets(str(exc))[:120])
        except sqlite3.Error as exc:
            raise RuntimeError('badquery:' + devtools.mask_secrets(str(exc))[:120])
        names = [d[0] for d in (cur.description or [])]
    finally:
        con.close()
    cut = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    lines = [' | '.join(names)]
    for r in rows:
        lines.append(' | '.join(_cell(n, v) for n, v in zip(names, r)))
    text = '\n'.join(lines)
    clipped = len(text) > MAX_TEXT
    return {'name': Path(path).name, 'db': Path(path).name, 'text': text[:MAX_TEXT], 'rows': len(rows), 'cut': cut or clipped}
