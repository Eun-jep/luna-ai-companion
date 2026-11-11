"""Exact numbers for tables. A language model counts and adds badly, so when the creator shows her a CSV or Excel file the program
reads the WHOLE file and computes the summary itself: rows, columns, types, totals, averages, extremes, gaps, duplicates, most common values.
She quotes these numbers instead of counting the few rows that fit in the text. Standard library plus openpyxl for Excel. Read-only."""
import csv
import io
import math
import re
import statistics
from datetime import date, datetime
from pathlib import Path

MAX_ROWS = 200000
MAX_COLS = 30
MAX_SHEETS = 3
TABLE_EXT = {'.csv', '.tsv', '.xlsx'}

_NUM_JUNK = re.compile(r'[\s  $€£₩₽¥%]')
_NUM = re.compile(r'^[+-]?(\d+(\.\d+)?|\.\d+)$')
_DATE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})([ T]\d{2}:\d{2}(:\d{2})?)?$|^(\d{2})\.(\d{2})\.(\d{4})$')


def number(v):
    """A float from a cell (handles '1 234,50', '12%', '$5', 3, 2.5) or None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if isinstance(v, float) and (math.isnan(v) or math.isinf(v)) else float(v)
    if not isinstance(v, str):
        return None
    s = _NUM_JUNK.sub('', v)
    if not s:
        return None
    if ',' in s and '.' in s:      # 1,234.50
        s = s.replace(',', '')
    else:
        s = s.replace(',', '.')
    if not _NUM.match(s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def when(v):
    """A date from a cell (datetime objects, ISO 2024-05-17, 17.05.2024) or None."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if not isinstance(v, str):
        return None
    m = _DATE.match(v.strip())
    if not m:
        return None
    try:
        if m.group(1):
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return date(int(m.group(8)), int(m.group(7)), int(m.group(6)))
    except ValueError:
        return None


def _fmt(x):
    if x == int(x) and abs(x) < 1e15:
        return '{:,}'.format(int(x)).replace(',', ' ')
    return ('{:,.4f}'.format(x).rstrip('0').rstrip('.')).replace(',', ' ')


def _empty(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _csv_rows(path):
    raw = Path(path).read_bytes()
    for enc in ('utf-8-sig', 'cp1251'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        text = raw.decode('utf-8', errors='replace')
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel_tab if path.lower().endswith('.tsv') else csv.excel
    rows = []
    for i, row in enumerate(csv.reader(io.StringIO(text), dialect)):
        if i >= MAX_ROWS:
            break
        rows.append(row)
    return [('', rows)]


def _xlsx_rows(path):
    import openpyxl
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    out = []
    try:
        for ws in wb.worksheets[:MAX_SHEETS]:
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= MAX_ROWS:
                    break
                rows.append(list(row))
            out.append((ws.title, rows))
    finally:
        wb.close()
    return out


def _header(rows):
    """(names, data rows): the first row is a header when it is all text and the next row has a number or date in it."""
    if not rows:
        return [], []
    first = [c for c in rows[0] if not _empty(c)]
    texty = bool(first) and all(number(c) is None and when(c) is None for c in first)
    width = max(len(r) for r in rows[:200])
    if texty:
        names = [str(c).strip() if not _empty(c) else 'колонка %d' % (i + 1) for i, c in enumerate(rows[0])]
        names += ['колонка %d' % (i + 1) for i in range(len(names), width)]
        return names, rows[1:]
    return ['колонка %d' % (i + 1) for i in range(width)], rows


def column(name, values):
    """One line about a column: type and exact facts."""
    filled = [v for v in values if not _empty(v)]
    gaps = len(values) - len(filled)
    tail = ', пустых %d' % gaps if gaps else ''
    if not filled:
        return '«%s»: пусто' % name
    nums = [number(v) for v in filled]
    if sum(n is not None for n in nums) >= 0.9 * len(filled):
        xs = [n for n in nums if n is not None]
        skipped = len(filled) - len(xs)
        extra = ', не число: %d' % skipped if skipped else ''
        return '«%s»: числа, %d значений, сумма %s, среднее %s, медиана %s, минимум %s, максимум %s%s%s' % (
            name, len(xs), _fmt(math.fsum(xs)), _fmt(math.fsum(xs) / len(xs)), _fmt(statistics.median(xs)), _fmt(min(xs)), _fmt(max(xs)), extra, tail)
    ds = [when(v) for v in filled]
    if sum(d is not None for d in ds) >= 0.9 * len(filled):
        xs = [d for d in ds if d]
        return '«%s»: даты, от %s до %s, %d значений%s' % (name, min(xs).isoformat(), max(xs).isoformat(), len(xs), tail)
    counts = {}
    for v in filled:
        k = str(v).strip()
        counts[k] = counts.get(k, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    shown = '; '.join('%s: %d' % (k[:40], n) for k, n in top)
    return '«%s»: текст, %d разных значений из %d%s. Чаще всего: %s' % (name, len(counts), len(filled), tail, shown)


def digest_rows(title, rows):
    names, data = _header(rows)
    if not data:
        return ''
    data = [list(r) + [None] * (len(names) - len(r)) for r in data if any(not _empty(c) for c in r)]
    if not data:
        return ''
    seen, dup = set(), 0
    for r in data:
        key = tuple('' if _empty(c) else str(c) for c in r)
        if key in seen:
            dup += 1
        seen.add(key)
    head = '%sстрок данных: %d, колонок: %d%s' % ('Лист «%s»: ' % title if title else '', len(data), len(names), ', полностью одинаковых строк: %d' % dup if dup else '')
    lines = [head]
    for i, n in enumerate(names[:MAX_COLS]):
        lines.append('- ' + column(n, [r[i] for r in data]))
    if len(names) > MAX_COLS:
        lines.append('- ещё колонок: %d (не показаны)' % (len(names) - MAX_COLS))
    return '\n'.join(lines)


def digest(path):
    """The exact summary of a table file as text, '' when it is not a table. RuntimeError('need:openpyxl'), OSError, ValueError."""
    ext = Path(path).suffix.lower()
    if ext not in TABLE_EXT:
        return ''
    if ext == '.xlsx':
        try:
            sheets = _xlsx_rows(path)
        except ImportError:
            raise RuntimeError('need:openpyxl')
    else:
        sheets = _csv_rows(str(path))
    parts = [d for d in (digest_rows(t, r) for t, r in sheets) if d]
    if not parts:
        return ''
    cut = ' Файл длиннее %d строк: считалось по первым.' % MAX_ROWS if any(len(r) >= MAX_ROWS for _, r in sheets) else ''
    return ('СВОДКА (посчитана программой по всему файлу, а не по тому, что поместилось в текст; этим числам можно доверять, '
            'суммы и количества бери отсюда и не пересчитывай сама).' + cut + '\n' + '\n\n'.join(parts))
