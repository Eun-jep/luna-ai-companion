"""Her hands, part 5: Word, PowerPoint and Excel documents.
The model never writes a file or code. In her reply she writes a fenced block ```lunadoc with a small JSON description (headings,
paragraphs, tables / slides / sheets); this module validates every field against fixed limits and renders it with python-docx,
python-pptx and openpyxl. The creator presses a plate first, files are only ever created in one folder (Documents\\Luna),
never overwrite an existing file, and Excel formulas are limited to a short list of harmless functions.
The document is written in a plain professional style; her warmth belongs to what she says around it."""
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

TTL, MAX_PER_MINUTE = 600, 10
MAX_JSON = 60000
PENDING = {}                     # token -> (spec, time): proposed by her, waiting for the creator's press
_recent = []
_lock = threading.Lock()


def _folder():
    docs = Path.home() / 'Documents'
    return (docs if docs.is_dir() else Path.home()) / 'Luna'


FOLDER = None                    # tests point this elsewhere
KINDS = {'docx': 'Word', 'pptx': 'PowerPoint', 'xlsx': 'Excel'}
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *('COM%d' % i for i in range(1, 10)), *('LPT%d' % i for i in range(1, 10))}
CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
FUNCS = {'SUM', 'AVERAGE', 'MIN', 'MAX', 'COUNT', 'COUNTA', 'ROUND', 'IF', 'ABS', 'SUMIF', 'COUNTIF', 'AVERAGEIF', 'PRODUCT'}
FORMULA_OK = re.compile(r'^=[A-Za-z0-9_(),.:+\-*/%^<>=&" $]{1,200}$')
HEX = re.compile(r'^[0-9A-Fa-f]{6}$')


def _text(v, limit=4000):
    if not isinstance(v, (str, int, float)) or isinstance(v, bool):
        raise ValueError('text')
    return CONTROL.sub('', str(v))[:limit].strip()


def _list(v, limit, item=None):
    if not isinstance(v, list) or len(v) > limit:
        raise ValueError('list')
    return [item(x) if item else x for x in v]


def _table(v):
    if not isinstance(v, dict):
        raise ValueError('table')
    header = _list(v.get('header', []), 30, lambda x: _text(x, 120))
    rows = _list(v.get('rows'), 500, lambda r: _list(r, 30, lambda x: _text(x, 400)))
    if not rows or any(len(r) > 30 for r in rows):
        raise ValueError('table')
    return {'header': header, 'rows': rows}


def _cell(v):
    """Excel cell: number, text, or a formula from the short safe list."""
    if isinstance(v, bool) or v is None:
        return '' if v is None else str(v)
    if isinstance(v, (int, float)):
        if abs(v) > 1e15:
            raise ValueError('number')
        return v
    s = _text(v, 1000)
    if s.startswith('='):
        names = re.findall(r'[A-Za-z][A-Za-z0-9.]*(?=\()', s)
        if not FORMULA_OK.match(s) or any(n.upper() not in FUNCS for n in names) or '!' in s or '[' in s:
            return {'text': s}   # not a formula she may write: shown as plain text
        return {'formula': s}
    return s


def _chart(v, sheets):
    if v is None:
        return None
    if not isinstance(v, dict) or v.get('type') not in ('bar', 'line', 'pie'):
        raise ValueError('chart')
    cols = _list(v.get('values', [2]), 5, lambda x: int(x))
    if not cols or any(not 1 <= c <= 30 for c in cols):
        raise ValueError('chart')
    return {'type': v['type'], 'title': _text(v.get('title', ''), 120), 'values': cols}


def parse(text):
    """The JSON from her block -> a validated, normalised spec (dict); ValueError for anything that is not in the contract."""
    if not isinstance(text, str) or len(text) > MAX_JSON:
        raise ValueError('size')
    data = json.loads(text)
    if not isinstance(data, dict) or data.get('type') not in KINDS:
        raise ValueError('type')
    kind = data['type']
    spec = {'type': kind, 'title': _text(data.get('title', ''), 120) or 'Document'}
    if kind == 'docx':
        blocks = []
        for b in _list(data.get('blocks'), 300):
            if not isinstance(b, dict):
                raise ValueError('block')
            if 'h' in b:
                level = int(b['h'])
                if level not in (1, 2, 3):
                    raise ValueError('h')
                blocks.append({'h': level, 'text': _text(b.get('text'), 300)})
            elif 'p' in b:
                blocks.append({'p': _text(b['p'], 5000)})
            elif 'ul' in b or 'ol' in b:
                key = 'ul' if 'ul' in b else 'ol'
                blocks.append({key: _list(b[key], 60, lambda x: _text(x, 500))})
            elif 'table' in b:
                blocks.append({'table': _table(b['table'])})
            elif b.get('pagebreak') is True:
                blocks.append({'pagebreak': True})
            else:
                raise ValueError('block')
        if not blocks:
            raise ValueError('empty')
        spec['blocks'] = blocks
        spec['subtitle'] = _text(data.get('subtitle', ''), 200)
    elif kind == 'pptx':
        slides = []
        for s in _list(data.get('slides'), 40):
            if not isinstance(s, dict):
                raise ValueError('slide')
            one = {'title': _text(s.get('title', ''), 150), 'layout': 'title' if s.get('layout') == 'title' else 'content',
                   'subtitle': _text(s.get('subtitle', ''), 200), 'notes': _text(s.get('notes', ''), 2000)}
            if 'bullets' in s:
                one['bullets'] = _list(s['bullets'], 8, lambda x: _text(x, 220))
            if 'text' in s:
                one['text'] = _text(s['text'], 900)
            if 'table' in s:
                t = _table(s['table'])
                if len(t['rows']) > 10 or len(t['header']) > 6 or any(len(r) > 6 for r in t['rows']):
                    raise ValueError('slide table')
                one['table'] = t
            slides.append(one)
        if not slides:
            raise ValueError('empty')
        spec['slides'] = slides
        if data.get('accent') is not None:
            if not isinstance(data['accent'], str) or not HEX.match(data['accent'].lstrip('#')):
                raise ValueError('accent')
            spec['accent'] = data['accent'].lstrip('#').upper()
    else:
        sheets = []
        for s in _list(data.get('sheets'), 10):
            if not isinstance(s, dict):
                raise ValueError('sheet')
            name = re.sub(r'[\[\]:*?/\\]', '', _text(s.get('name', ''), 31)) or 'Sheet%d' % (len(sheets) + 1)
            rows = _list(s.get('rows'), 2000, lambda r: _list(r, 30, _cell))
            if not rows:
                raise ValueError('empty')
            sheets.append({'name': name[:31], 'header': _list(s.get('header', []), 30, lambda x: _text(x, 120)), 'rows': rows,
                           'chart': _chart(s.get('chart'), None)})
        if not sheets:
            raise ValueError('empty')
        spec['sheets'] = sheets
    return spec


def describe(spec):
    """How much there is: blocks, slides or sheets (the page words it in the interface language)."""
    return len(spec.get({'docx': 'blocks', 'pptx': 'slides', 'xlsx': 'sheets'}[spec['type']]))


def propose(text):
    """Her block -> a plate for the page {token, kind, name, size}, or None if it is not a document the contract allows."""
    try:
        spec = parse(text)
    except (ValueError, TypeError, KeyError):
        return None
    now = time.time()
    with _lock:
        for k in [k for k, v in PENDING.items() if now - v[1] > TTL]:
            del PENDING[k]
        if len(PENDING) >= 20:
            return None
        token = secrets.token_urlsafe(12)
        PENDING[token] = (spec, now)
    return {'token': token, 'kind': spec['type'], 'app': KINDS[spec['type']], 'title': spec['title'], 'size': describe(spec),
            'name': _filename(spec, check=False)}


def take(token):
    with _lock:
        entry = PENDING.pop(token, None)
    return entry[0] if entry and time.time() - entry[1] <= TTL else None


def _safe_name(title):
    name = re.sub(r'[\\/:*?"<>|]', '', CONTROL.sub('', title)).strip(' .')[:60].strip(' .') or 'Document'
    return '_' + name if name.upper() in RESERVED else name


def _filename(spec, check=True):
    folder = FOLDER or _folder()
    base, ext = _safe_name(spec['title']), '.' + spec['type']
    path = folder / (base + ext)
    n = 2
    while check and path.exists():
        path = folder / ('%s (%d)%s' % (base, n, ext))
        n += 1
    return path.name if not check else path


# ---- rendering ----

def _runs(par, text):
    """**bold** and *italic* inside a paragraph."""
    for part in re.split(r'(\*\*[^*]+\*\*|\*[^*]+\*)', text):
        if part.startswith('**') and part.endswith('**') and len(part) > 4:
            par.add_run(part[2:-2]).bold = True
        elif part.startswith('*') and part.endswith('*') and len(part) > 2:
            par.add_run(part[1:-1]).italic = True
        elif part:
            par.add_run(part)


def _plain(text):
    return re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)


def _docx(spec, path):
    from docx import Document
    from docx.shared import Pt
    doc = Document()
    doc.styles['Normal'].font.name = 'Calibri'
    doc.styles['Normal'].font.size = Pt(11)
    doc.add_heading(spec['title'], 0)
    if spec['subtitle']:
        p = doc.add_paragraph()
        p.add_run(spec['subtitle']).italic = True
    for b in spec['blocks']:
        if 'h' in b:
            doc.add_heading(b['text'], b['h'])
        elif 'p' in b:
            _runs(doc.add_paragraph(), b['p'])
        elif 'ul' in b or 'ol' in b:
            style = 'List Bullet' if 'ul' in b else 'List Number'
            for item in b.get('ul') or b.get('ol'):
                _runs(doc.add_paragraph(style=style), item)
        elif 'table' in b:
            t = b['table']
            cols = max([len(t['header'])] + [len(r) for r in t['rows']])
            table = doc.add_table(rows=0, cols=cols)
            table.style = 'Light Grid Accent 1'
            if t['header']:
                cells = table.add_row().cells
                for i, h in enumerate(t['header']):
                    cells[i].text = h
                    for r in cells[i].paragraphs[0].runs:
                        r.bold = True
            for row in t['rows']:
                cells = table.add_row().cells
                for i, v in enumerate(row):
                    cells[i].text = v
            doc.add_paragraph()
        elif b.get('pagebreak'):
            doc.add_page_break()
    doc.core_properties.title = spec['title']
    doc.core_properties.author = 'Luna'
    doc.save(str(path))


def _pptx(spec, path):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu, Inches, Pt
    accent = RGBColor.from_string(spec.get('accent', '3B6FD4'))
    dark = RGBColor(0x22, 0x2B, 0x3A)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    W, H = prs.slide_width, prs.slide_height

    def place(shape, l, t, w, h):
        shape.left, shape.top, shape.width, shape.height = Emu(int(l)), Emu(int(t)), Emu(int(w)), Emu(int(h))

    def style(frame, size, color=dark, bold=False):
        for p in frame.paragraphs:
            for r in p.runs:
                r.font.size, r.font.bold, r.font.color.rgb = Pt(size), bold, color

    for i, s in enumerate(spec['slides']):
        if s['layout'] == 'title' or (i == 0 and 'bullets' not in s and 'text' not in s and 'table' not in s):
            slide = prs.slides.add_slide(prs.slide_layouts[0])
            band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, int(H * 0.06))
            band.fill.solid(); band.fill.fore_color.rgb = accent; band.line.fill.background()
            slide.shapes.title.text = s['title'] or spec['title']
            place(slide.shapes.title, W * 0.08, H * 0.28, W * 0.84, H * 0.22)
            style(slide.shapes.title.text_frame, 44, accent, True)
            sub = slide.placeholders[1]
            sub.text = s['subtitle']
            place(sub, W * 0.08, H * 0.54, W * 0.84, H * 0.16)
            style(sub.text_frame, 24)
        else:
            slide = prs.slides.add_slide(prs.slide_layouts[5])   # title only; the body is drawn by hand for a 16:9 page
            bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, int(W * 0.012), H)
            bar.fill.solid(); bar.fill.fore_color.rgb = accent; bar.line.fill.background()
            slide.shapes.title.text = s['title']
            place(slide.shapes.title, W * 0.06, H * 0.05, W * 0.88, H * 0.16)
            style(slide.shapes.title.text_frame, 32, accent, True)
            slide.shapes.title.text_frame.paragraphs[0].alignment = 1
            body = (W * 0.06, H * 0.25, W * 0.88, H * 0.65)
            if s.get('table'):
                t = s['table']
                cols = max([len(t['header'])] + [len(r) for r in t['rows']])
                rows = len(t['rows']) + (1 if t['header'] else 0)
                shape = slide.shapes.add_table(rows, cols, Emu(int(body[0])), Emu(int(body[1])), Emu(int(body[2])), Emu(int(min(body[3], 0.5 * 914400 * rows))))
                grid, r0 = shape.table, 0
                if t['header']:
                    for j, h in enumerate(t['header']):
                        grid.cell(0, j).text = h
                    r0 = 1
                for r, row in enumerate(t['rows']):
                    for j, v in enumerate(row):
                        grid.cell(r + r0, j).text = v
                for r in range(rows):
                    for j in range(cols):
                        for par in grid.cell(r, j).text_frame.paragraphs:
                            for run in par.runs:
                                run.font.size = Pt(16)
            else:
                items = s.get('bullets') or ([s['text']] if s.get('text') else [])
                box = slide.shapes.add_textbox(*(Emu(int(x)) for x in body))
                frame = box.text_frame
                frame.word_wrap = True
                total = sum(len(x) for x in items)
                size = 26 if total < 260 and len(items) <= 5 else 22 if total < 520 else 18
                for k, item in enumerate(items):
                    par = frame.paragraphs[0] if k == 0 else frame.add_paragraph()
                    par.text = ('•  ' if s.get('bullets') else '') + _plain(item)
                    par.space_after = Pt(10)
                    for r in par.runs:
                        r.font.size, r.font.color.rgb = Pt(size), dark
        if s['notes']:
            slide.notes_slide.notes_text_frame.text = s['notes']
    prs.core_properties.title = spec['title']
    prs.core_properties.author = 'Luna'
    prs.save(str(path))


def _xlsx(spec, path):
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    wb.remove(wb.active)
    for s in spec['sheets']:
        ws = wb.create_sheet(s['name'])
        r0 = 1
        if s['header']:
            ws.append(s['header'])
            for c in ws[1]:
                c.font = Font(bold=True, color='FFFFFF')
                c.fill = PatternFill('solid', fgColor='3B6FD4')
                c.alignment = Alignment(horizontal='center')
            ws.freeze_panes = 'A2'
            r0 = 2
        for i, row in enumerate(s['rows']):
            r = r0 + i
            for j, v in enumerate(row, 1):
                cell = ws.cell(r, j)
                if isinstance(v, dict):
                    if 'formula' in v:
                        cell.value = v['formula']
                    else:
                        cell.value = v['text']
                        cell.data_type = 's'   # text that starts with "=" but is not an allowed formula stays text
                else:
                    cell.value = v
        for j in range(1, max([len(s['header'])] + [len(r) for r in s['rows']]) + 1):
            longest = 8
            for cell in ws[get_column_letter(j)]:
                v = cell.value
                if isinstance(v, str) and not v.startswith('='):
                    longest = max(longest, min(60, len(v) + 2))
            ws.column_dimensions[get_column_letter(j)].width = longest
        if s['chart']:
            ch = s['chart']
            kind = {'bar': BarChart, 'line': LineChart, 'pie': PieChart}[ch['type']]()
            kind.title = ch['title'] or None
            last = r0 + len(s['rows']) - 1
            for col in ch['values']:
                kind.add_data(Reference(ws, min_col=col, min_row=r0 - 1 if s['header'] else r0, max_row=last), titles_from_data=bool(s['header']))
            kind.set_categories(Reference(ws, min_col=1, min_row=r0, max_row=last))
            kind.width, kind.height = 18, 9
            ws.add_chart(kind, 'H2')
    wb.properties.title = spec['title']
    wb.properties.creator = 'Luna'
    wb.save(str(path))


RENDER = {'docx': _docx, 'pptx': _pptx, 'xlsx': _xlsx}
LIBS = {'docx': 'python-docx', 'pptx': 'python-pptx', 'xlsx': 'openpyxl'}


def make(token, open_after=False):
    """Create the file the creator agreed to. Returns {name, folder, opened}. Errors: PermissionError('token'), RuntimeError('nolib|<package>'),
    RuntimeError('rate'), OSError."""
    spec = take(token)
    if not spec:
        raise PermissionError('token')
    now = time.time()
    with _lock:
        _recent[:] = [t for t in _recent if now - t < 60]
        if len(_recent) >= MAX_PER_MINUTE:
            raise RuntimeError('rate')
        _recent.append(now)
    folder = FOLDER or _folder()
    folder.mkdir(parents=True, exist_ok=True)
    path = _filename(spec)
    try:
        RENDER[spec['type']](spec, path)
    except ImportError:
        raise RuntimeError('nolib|' + LIBS[spec['type']]) from None
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise RuntimeError('render') from None
    opened = False
    if open_after and hasattr(os, 'startfile'):
        try:
            os.startfile(str(path))
            opened = True
        except OSError:
            pass
    return {'name': path.name, 'folder': str(folder), 'opened': opened}
