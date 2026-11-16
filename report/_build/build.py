"""Builds the report, the code guide and the deck (PDF, DOCX, PPTX) in English and Korean from content.py.

    python report/_build/build.py            everything
    python report/_build/build.py en         one language

Needs python-docx, python-pptx, Pillow and Playwright with Edge (the PDF and the diagram are made from HTML by Edge).
The numbers (lines, modules, tests) are measured from the repository every time, so they cannot go stale.
"""
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
REPORT = ROOT / 'report'
ASSETS = REPORT / 'assets'
sys.path.insert(0, str(HERE))
from content import C, DATE, VERSION  # noqa: E402

INK, VIOLET, LAV, MIST, DARK, MID, ROSE = '1b1235', '5b2fc9', 'cdb8ff', 'f4f0ff', '0e0a24', '2a1a5e', 'a23cc4'
EDGE = next((p for p in (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe') if os.path.exists(p)), None)
NAMES = {
    'en': dict(report='Luna - Project Report', guide='Luna - Code Guide for the Defense', deck='Luna - Presentation'),
    'ko': dict(report='루나 - 프로젝트 보고서', guide='루나 - 코드 설명서 (발표 심사용)', deck='루나 - 발표 자료'),
}
GROUPS = {
    'en': [('app.py', 'The conductor'), ('luna/server', 'Server parts'), ('luna/core', 'Core: who she is'), ('luna/security.py', 'Core: who she is'), ('luna/paths.py', 'Core: who she is'),
           ('luna/skills', 'Skills: exact abilities'), ('luna/senses', 'Senses'), ('luna/hands', 'Hands'), ('luna/dev', 'Developer tools'),
           ('web/', 'The page'), ('desktop/', 'The page'), ('tools/', 'Tools')],
    'ko': [('app.py', '지휘자'), ('luna/server', '서버 부분'), ('luna/core', '핵심: 루나가 누구인가'), ('luna/security.py', '핵심: 루나가 누구인가'), ('luna/paths.py', '핵심: 루나가 누구인가'),
           ('luna/skills', '기능: 정확한 능력'), ('luna/senses', '감각'), ('luna/hands', '손'), ('luna/dev', '개발자 도구'),
           ('web/', '페이지'), ('desktop/', '페이지'), ('tools/', '도구')],
}
HEAD = {'en': ('File', 'Lines', 'What it does'), 'ko': ('파일', '줄 수', '하는 일')}


# ------------------------------------------------------------------------------------------------ measuring
def git(*a):
    return subprocess.check_output(['git', *a], cwd=ROOT, text=True, encoding='utf-8').split('\n')


def lines_of(files):
    return sum((ROOT / f).read_text(encoding='utf-8', errors='ignore').count('\n') + 1 for f in files if f)


def measure():
    tracked = [f for f in git('ls-files') if f]
    py = [f for f in tracked if f.endswith('.py') and not f.startswith(('tests/', 'report/'))]
    js = [f for f in tracked if f.endswith('.js') and re.match(r'(web|desktop)/[^/]+\.js$', f)]
    tests = [f for f in tracked if f.startswith('tests/') and f.endswith('.py')]
    mods = [f for f in py if f.startswith(('luna/', 'app.py')) and not f.endswith('__init__.py')]
    area = lambda a: len([f for f in mods if f.startswith('luna/%s/' % a)])
    legacy = json.loads((ROOT / 'tests' / 'legacy_counts.json').read_text(encoding='utf-8'))
    out = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8').stdout
    pytests = sum(int(m.group(1)) for m in re.finditer(r'^tests/\S+: (\d+)$', out, re.M))
    fmt = lambda n: '{:,}'.format(n)
    return {
        'py': fmt(lines_of(py)), 'js': fmt(lines_of(js)), 'mods': str(len(mods)), 'tests_lines': fmt(lines_of(tests)),
        'pytests': str(pytests), 'legacy': fmt(sum(legacy.values())), 'nsuites': str(len(legacy)), 'checks': fmt(pytests + sum(legacy.values())),
        'n_core': str(area('core')), 'n_skills': str(area('skills')), 'n_senses': str(area('senses')), 'n_hands': str(area('hands')), 'n_dev': str(area('dev')), 'n_server': str(area('server')),
    }


def fill(text, m):
    return re.sub(r'\{(\w+)\}', lambda x: m.get(x.group(1), x.group(0)), text)


def module_rows(c, m):
    groups, order = {}, []
    for path, desc in c['modules']:
        name = next(g for p, g in GROUPS[c['lang']] if path == p or path.startswith(p if p.endswith('/') or p.endswith('.py') else p + '/'))
        n = lines_of([path])
        if name not in groups:
            groups[name] = []
            order.append(name)
        groups[name].append([path, '{:,}'.format(n), desc])
    return [(g, groups[g]) for g in order]


# ------------------------------------------------------------------------------------------------ diagram (HTML -> PNG)
def diagram_html(c):
    d = c['diagram']
    box = lambda k, cls='': '<div class="box %s"><b>%s</b>%s</div>' % (cls, html.escape(d[k][0]), ''.join('<span>%s</span>' % html.escape(x) for x in d[k][1]))
    return '''<!doctype html><meta charset=utf-8><style>
body{margin:0;width:1600px;height:640px;background:linear-gradient(160deg,#0e0a24,#241454 60%%,#37207e);font-family:'Segoe UI','Malgun Gothic',sans-serif;color:#efe8ff;position:relative;overflow:hidden}
.row{position:absolute;left:50px;right:50px;top:70px;display:flex;align-items:center;justify-content:space-between}
.box{width:300px;padding:26px 20px;border:2px solid #7a56e0;border-radius:18px;background:rgba(40,24,98,.75);box-shadow:0 0 28px rgba(150,110,255,.35);text-align:center}
.box b{display:block;font:700 30px Georgia,'Malgun Gothic',serif;color:#cdb8ff;margin-bottom:12px}
.box span{display:block;font-size:21px;line-height:1.5;color:#e6dcff}
.arrow{font-size:54px;color:#a58bff}
.col{display:flex;flex-direction:column;gap:22px}
.col .box{width:330px;padding:18px 16px}
.net{border-color:#c67be0}
.press{position:absolute;left:50px;right:50px;bottom:48px;height:92px;border:2px dashed #cdb8ff;border-radius:46px;display:flex;align-items:center;justify-content:center;gap:30px;background:rgba(205,184,255,.08)}
.press b{font:700 30px Georgia,'Malgun Gothic',serif;color:#fff}.press span{font-size:23px;color:#cdb8ff}
.moon{position:absolute;right:26px;top:14px;font-size:40px;color:#cdb8ff}
</style><body><div class=moon>&#9790;</div>
<div class=row>%s<div class=arrow>&#10132;</div>%s<div class=arrow>&#10132;</div><div class=col>%s%s</div><div class=arrow>&#10132;</div>%s</div>
<div class=press><b>%s</b><span>%s</span></div></body>''' % (
        box('screen'), box('server'), box('brain'), box('body'), box('net', 'net'),
        html.escape(d['press'][0]), html.escape(' '.join(d['press'][1])))


def make_diagram(c, browser, out):
    page = browser.new_page(viewport={'width': 1600, 'height': 640})
    page.set_content(diagram_html(c))
    page.wait_for_timeout(300)
    page.screenshot(path=str(out))
    page.close()


# ------------------------------------------------------------------------------------------------ HTML / PDF
CSS = '''
@page{size:A4;margin:20mm 18mm 20mm 18mm}
@page cover{margin:0}
*{box-sizing:border-box}
body{margin:0;font:10.5pt/1.55 'Segoe UI','Malgun Gothic',sans-serif;color:#%(ink)s;background:#fff}
.cover{page:cover;height:297mm;background:#%(dark)s;position:relative;break-after:page;overflow:hidden}
.cover img{width:210mm;display:block}
.cover .panel{position:absolute;left:0;right:0;top:118mm;bottom:0;padding:18mm 20mm;background:linear-gradient(180deg,#%(dark)s,#1d1049 70%%,#2a1a5e)}
.cover .panel:before{content:'';position:absolute;left:20mm;right:20mm;top:0;height:2px;background:linear-gradient(90deg,transparent,#%(lav)s,transparent)}
.cover h1{font:700 40pt/1.1 Georgia,'Malgun Gothic',serif;color:#fff;margin:0 0 4mm;letter-spacing:.5pt}
.cover h2{font:400 21pt Georgia,'Malgun Gothic',serif;color:#%(lav)s;margin:0 0 10mm}
.cover p{margin:0 0 3mm;color:#d9ccff;font-size:12pt;max-width:150mm}
.cover .by{position:absolute;left:20mm;bottom:16mm;color:#%(lav)s;font:italic 14pt Georgia,'Malgun Gothic',serif}
.cover .by b{font-style:normal;color:#fff;letter-spacing:1pt}
h1.s{font:700 20pt Georgia,'Malgun Gothic',serif;color:#%(violet)s;margin:9mm 0 4mm;padding-bottom:2mm;border-bottom:2px solid #%(lav)s;break-after:avoid}
h1.s:before{content:'\\263E';color:#%(rose)s;margin-right:3mm}
h2.s{font:700 13pt Georgia,'Malgun Gothic',serif;color:#%(mid)s;margin:6mm 0 2mm;break-after:avoid}
p{margin:0 0 3mm}
ul{margin:0 0 4mm;padding-left:6mm}li{margin:0 0 1.6mm}li::marker{color:#%(rose)s}
table{width:100%%;border-collapse:collapse;margin:2mm 0 5mm;font-size:9.5pt}
th{background:#%(violet)s;color:#fff;text-align:left;padding:2.2mm 3mm;font-weight:600}
td{padding:2mm 3mm;border-bottom:1px solid #e3dbff;vertical-align:top}
tr:nth-child(even) td{background:#%(mist)s}
td:first-child{font-weight:600;color:#%(mid)s;white-space:nowrap}
tr{break-inside:avoid}
.stats{break-inside:avoid;display:flex;gap:4mm;margin:5mm 0}
.stat{flex:1;background:linear-gradient(160deg,#%(dark)s,#2a1a5e);border-radius:3mm;padding:5mm 3mm;text-align:center;color:#d9ccff;font-size:9pt;border:1px solid #6d3fd6}
.stat b{display:block;font:700 22pt Georgia,serif;color:#%(lav)s;margin-bottom:1mm}
figure{margin:4mm 0 6mm;break-inside:avoid;text-align:center}
figure img{width:80%%;border-radius:3mm;border:1px solid #b9a2ff;box-shadow:0 2mm 6mm rgba(60,30,140,.35)}
figcaption{font:italic 9.5pt Georgia,'Malgun Gothic',serif;color:#5b4a96;margin-top:2mm}
.q{margin:0 0 4mm;break-inside:avoid}.q b{display:block;color:#%(violet)s}
.grp{break-inside:avoid}
.intro{background:#%(mist)s;border-left:4px solid #%(violet)s;padding:3mm 4mm;margin:0 0 4mm;border-radius:0 2mm 2mm 0}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.f{font-family:Consolas,monospace;font-size:8.8pt;white-space:nowrap}
''' % dict(ink=INK, dark=DARK, lav=LAV, violet=VIOLET, rose=ROSE, mid=MID, mist=MIST)


def esc(t):
    return html.escape(t)


def blocks_html(blocks, c, m, lang, assets_rel):
    out = []
    for b in blocks:
        k = b[0]
        if k == 'h1':
            out.append('<h1 class=s>%s</h1>' % esc(b[1]))
        elif k == 'h2':
            out.append('<h2 class=s>%s</h2>' % esc(b[1]))
        elif k == 'p':
            out.append('<p>%s</p>' % esc(fill(b[1], m)))
        elif k == 'ul':
            out.append('<ul>%s</ul>' % ''.join('<li>%s</li>' % esc(fill(x, m)) for x in b[1]))
        elif k == 'table':
            out.append('<table><tr>%s</tr>%s</table>' % (''.join('<th>%s</th>' % esc(h) for h in b[1]),
                       ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % esc(fill(x, m)) for x in r) for r in b[2])))
        elif k == 'stats':
            out.append('<div class=stats>%s</div>' % ''.join('<div class=stat><b>%s</b>%s</div>' % (esc(fill(n, m)), esc(fill(l, m))) for n, l in b[1]))
        elif k == 'shot':
            out.append('<figure><img src="%s/screens/%s-%s.jpg"><figcaption>%s</figcaption></figure>' % (assets_rel, c['shots_dir'], b[1], esc(b[2])))
        elif k == 'diagram':
            out.append('<figure><img src="../assets/diagram-%s.png"></figure>' % lang)
        elif k == 'qa':
            out.append(''.join('<div class=q><b>%s</b>%s</div>' % (esc(q), esc(a)) for q, a in b[1]))
        elif k == 'modules':
            for g, rows in b[1]:
                out.append('<div class=grp><h2 class=s>%s</h2><table><tr><th>%s</th><th>%s</th><th>%s</th></tr>%s</table></div>' % (
                    esc(g), *map(esc, HEAD[lang]), ''.join('<tr><td class=f>%s</td><td class=n>%s</td><td style="font-weight:400;white-space:normal">%s</td></tr>' % tuple(map(esc, r)) for r in rows)))
    return '\n'.join(out)


def cover_html(c, title):
    return '''<section class=cover><img src="%s"><div class=panel><h1>%s</h1><h2>%s</h2><p>%s</p><p>%s</p><div class=by>%s<br><b>%s</b></div></div></section>''' % (
        'assets/moonlight-team.jpg', esc(c['app']), esc(title), esc(c['tagline']), esc(c['version'].format(v=VERSION, d=DATE[c['lang']])),
        'Prepared by' if c['lang'] == 'en' else '작성', esc(c['team'].upper() if c['lang'] == 'en' else c['team']))


def doc_blocks(kind, c, m):
    if kind == 'report':
        return c['report']
    mods = [('modules', module_rows(c, m))]
    return [('p_intro', c['guide_intro'])] + c['guide_pre'] + mods + c['guide_post']


def page_html(kind, c, m, lang):
    title = c['t_report'] if kind == 'report' else c['t_guide']
    body = []
    for b in doc_blocks(kind, c, m):
        if b[0] == 'p_intro':
            body.append('<div class=intro>%s</div>' % esc(b[1]))
        else:
            body.append(blocks_html([b], c, m, lang, 'assets'))
    return '<!doctype html><html lang=%s><meta charset=utf-8><title>%s</title><style>%s</style><body>%s<main>%s</main></body></html>' % (
        lang, esc(title), CSS, cover_html(c, title), '\n'.join(body))


def make_pdf(kind, c, m, lang, browser, out):
    tmp = REPORT / lang / ('_tmp_%s.html' % kind)
    # the page lives next to the assets so that relative links work: report/<lang>/ -> ../assets
    html_text = page_html(kind, c, m, lang).replace('src="assets/', 'src="../assets/').replace('src="../assets/screens', 'src="../assets/screens')
    tmp.write_text(html_text, encoding='utf-8')
    page = browser.new_page()
    page.goto(tmp.as_uri())
    page.wait_for_timeout(800)
    footer = '<div style="width:100%%;font:8px Georgia,serif;color:#6b5aa8;text-align:center">%s &nbsp;·&nbsp; %s &nbsp;·&nbsp; <span class="pageNumber"></span></div>' % (esc(c['app']), esc(c['team']))
    page.pdf(path=str(out), prefer_css_page_size=True, print_background=True, display_header_footer=True, header_template='<span></span>', footer_template=footer)
    page.close()
    tmp.unlink()


# ------------------------------------------------------------------------------------------------ DOCX
def build_docx(kind, c, m, lang, diagram_png, out):
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    rgb = lambda h: RGBColor.from_string(h.upper())
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2)
    sec.top_margin = sec.bottom_margin = Cm(2)

    def setfont(style, west, east, size=None, color=None, bold=None):
        f = style.font
        f.name = west
        style.element.rPr.rFonts.set(qn('w:eastAsia'), east)
        if size:
            f.size = Pt(size)
        if color:
            f.color.rgb = rgb(color)
        if bold is not None:
            f.bold = bold

    setfont(doc.styles['Normal'], 'Segoe UI', 'Malgun Gothic', 10.5, INK)
    doc.styles['Normal'].paragraph_format.space_after = Pt(6)
    for name, size, col in (('Heading 1', 20, VIOLET), ('Heading 2', 13, MID)):
        st = doc.styles[name]
        setfont(st, 'Georgia', 'Malgun Gothic', size, col, True)
        st.paragraph_format.space_before = Pt(18 if name == 'Heading 1' else 12)
        st.paragraph_format.space_after = Pt(6)
        st.paragraph_format.keep_with_next = True

    def shade(cell, color):
        pr = cell._tc.get_or_add_tcPr()
        sh = OxmlElement('w:shd')
        sh.set(qn('w:val'), 'clear'); sh.set(qn('w:color'), 'auto'); sh.set(qn('w:fill'), color)
        pr.append(sh)

    def borders(table, color=LAV):
        tbl = table._tbl.tblPr
        b = OxmlElement('w:tblBorders')
        for e in ('top', 'bottom', 'insideH'):
            x = OxmlElement('w:' + e)
            x.set(qn('w:val'), 'single'); x.set(qn('w:sz'), '4'); x.set(qn('w:color'), color)
            b.append(x)
        tbl.append(b)

    def cell_text(cell, text, bold=False, color=None, size=None, font=None, align=None):
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        if align:
            p.alignment = align
        r = p.add_run(text)
        r.bold = bold
        if color:
            r.font.color.rgb = rgb(color)
        if size:
            r.font.size = Pt(size)
        if font:
            r.font.name = font
            r._element.rPr.rFonts.set(qn('w:eastAsia'), 'Malgun Gothic')

    # --- cover: the team artwork, then a dark title panel
    title = c['t_report'] if kind == 'report' else c['t_guide']
    doc.add_picture(str(ASSETS / 'moonlight-team.jpg'), width=Cm(17))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = t.rows[0].cells[0]
    shade(cell, DARK)
    cell_text(cell, '', size=4)
    for text, size, col, bold, font in ((c['app'], 34, 'FFFFFF', True, 'Georgia'), (title, 20, LAV, False, 'Georgia'), ('', 8, LAV, False, None),
                                        (c['tagline'], 11, 'D9CCFF', False, None), (c['version'].format(v=VERSION, d=DATE[lang]), 11, 'D9CCFF', False, None),
                                        ('', 8, LAV, False, None), (('Prepared by  ' if lang == 'en' else '작성  ') + c['team'], 14, LAV, True, 'Georgia')):
        p = cell.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.6)
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(text)
        r.font.size = Pt(size); r.font.color.rgb = rgb(col); r.bold = bold
        if font:
            r.font.name = font
            r._element.rPr.rFonts.set(qn('w:eastAsia'), 'Malgun Gothic')
    doc.add_page_break()

    # --- footer with the page number
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = fp.add_run('%s  ·  %s  ·  ' % (c['app'], c['team']))
    r.font.size = Pt(8); r.font.color.rgb = rgb('6B5AA8')
    r2 = fp.add_run()
    r2.font.size = Pt(8); r2.font.color.rgb = rgb('6B5AA8')
    for tag, txt in (('begin', None), (None, 'PAGE'), ('end', None)):
        if tag:
            e = OxmlElement('w:fldChar'); e.set(qn('w:fldCharType'), tag)
        else:
            e = OxmlElement('w:instrText'); e.set(qn('xml:space'), 'preserve'); e.text = txt
        r2._r.append(e)

    def table(head, rows, widths=None, mono=False, numcol=None):
        tb = doc.add_table(rows=1, cols=len(head))
        tb.alignment = WD_TABLE_ALIGNMENT.CENTER
        borders(tb)
        for i, h in enumerate(head):
            shade(tb.rows[0].cells[i], VIOLET)
            cell_text(tb.rows[0].cells[i], h, True, 'FFFFFF', 9.5)
        for n, row in enumerate(rows):
            cells = tb.add_row().cells
            for i, v in enumerate(row):
                if n % 2 == 1:
                    shade(cells[i], MIST)
                cell_text(cells[i], v, bold=(i == 0 and not mono), color=(MID if i == 0 and not mono else None), size=9.5 if not (mono and i == 0) else 8.5,
                          font='Consolas' if (mono and i == 0) else None, align=WD_ALIGN_PARAGRAPH.RIGHT if i == numcol else None)
        if widths:
            for row in tb.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Cm(w)
        doc.add_paragraph().paragraph_format.space_after = Pt(2)

    for b in doc_blocks(kind, c, m):
        k = b[0]
        if k == 'h1':
            doc.add_heading('☾  ' + b[1], 1)
        elif k == 'h2':
            doc.add_heading(b[1], 2)
        elif k == 'p':
            doc.add_paragraph(fill(b[1], m))
        elif k == 'p_intro':
            t1 = doc.add_table(rows=1, cols=1)
            shade(t1.rows[0].cells[0], MIST)
            cell_text(t1.rows[0].cells[0], b[1], size=10)
            doc.add_paragraph()
        elif k == 'ul':
            for x in b[1]:
                doc.add_paragraph(fill(x, m), style='List Bullet')
        elif k == 'table':
            table(b[1], [[fill(x, m) for x in r] for r in b[2]], widths=[3.4, 13.6] if len(b[1]) == 2 else [3, 10.5, 3.5])
        elif k == 'stats':
            t2 = doc.add_table(rows=1, cols=len(b[1]))
            t2.alignment = WD_TABLE_ALIGNMENT.CENTER
            for i, (n, l) in enumerate(b[1]):
                cl = t2.rows[0].cells[i]
                shade(cl, DARK)
                cell_text(cl, fill(n, m), True, LAV, 20, 'Georgia', WD_ALIGN_PARAGRAPH.CENTER)
                p = cl.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                rr = p.add_run(fill(l, m)); rr.font.size = Pt(8.5); rr.font.color.rgb = rgb('D9CCFF')
            doc.add_paragraph()
        elif k == 'shot':
            doc.add_picture(str(ASSETS / 'screens' / ('%s-%s.jpg' % (c['shots_dir'], b[1]))), width=Cm(15.5))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            doc.paragraphs[-1].paragraph_format.keep_with_next = True
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            rr = p.add_run(b[2]); rr.italic = True; rr.font.size = Pt(9.5); rr.font.color.rgb = rgb('5B4A96')
        elif k == 'diagram':
            doc.add_picture(str(diagram_png), width=Cm(17))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif k == 'qa':
            for q, a in b[1]:
                p = doc.add_paragraph()
                p.paragraph_format.keep_with_next = True
                p.paragraph_format.space_after = Pt(1)
                rr = p.add_run(q); rr.bold = True; rr.font.color.rgb = rgb(VIOLET)
                doc.add_paragraph(a)
        elif k == 'modules':
            for g, rows in b[1]:
                doc.add_heading(g, 2)
                table(HEAD[lang], rows, widths=[4.6, 1.5, 10.9], mono=True, numcol=1)
    doc.core_properties.title = '%s - %s' % (c['app'], title)
    doc.core_properties.author = c['team']
    doc.save(str(out))


# ------------------------------------------------------------------------------------------------ PPTX
def build_pptx(c, m, lang, diagram_png, out):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Emu, Inches, Pt

    rgb = lambda h: RGBColor.from_string(h.upper())
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    western = 'Georgia'
    body_font = 'Segoe UI'

    def bg(slide, color=DARK):
        f = slide.background.fill
        f.solid()
        f.fore_color.rgb = rgb(color)

    def rect(slide, x, y, w, h, fill=None, line=None, alpha=None, shape=MSO_SHAPE.RECTANGLE, lw=1.5):
        s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
        if fill:
            s.fill.solid()
            s.fill.fore_color.rgb = rgb(fill)
            if alpha is not None:
                clr = s.fill._xPr.find(qn('a:solidFill')).find(qn('a:srgbClr'))
                a = clr.makeelement(qn('a:alpha'), {'val': str(int(alpha * 1000))})
                clr.append(a)
        else:
            s.fill.background()
        if line:
            s.line.color.rgb = rgb(line)
            s.line.width = Pt(lw)
        else:
            s.line.fill.background()
        s.shadow.inherit = False
        return s

    def text(slide, x, y, w, h, t, size=18, color='EFE8FF', bold=False, font=body_font, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False):
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = Inches(0.05)
        p = tf.paragraphs[0]
        p.alignment = align
        r = p.add_run()
        r.text = t
        r.font.size, r.font.bold, r.font.italic, r.font.name = Pt(size), bold, italic, font
        r.font.color.rgb = rgb(color)
        r._r.get_or_add_rPr().append(r._r.makeelement(qn('a:ea'), {'typeface': 'Malgun Gothic'}))
        return tb

    def chrome(slide, n, total):
        rect(slide, 0, 0, 0.14, 7.5, fill=VIOLET)
        rect(slide, 0.14, 0, 0.04, 7.5, fill=LAV, alpha=60)
        text(slide, 0.6, 7.0, 7, 0.35, '%s  ·  %s' % (c['app'], c['team']), 10, '8F7BD6')
        text(slide, 11.7, 7.0, 1.2, 0.35, '%d / %d' % (n, total), 10, '8F7BD6', align=PP_ALIGN.RIGHT)

    def heading(slide, t):
        text(slide, 0.6, 0.45, 12, 0.9, t, 34, LAV, True, western)
        rect(slide, 0.65, 1.38, 2.2, 0.05, fill=ROSE)

    def picture_frame(slide, path, x, y, w):
        from PIL import Image
        iw, ih = Image.open(path).size
        h = w * ih / iw
        rect(slide, x - 0.06, y - 0.06, w + 0.12, h + 0.12, fill=MID, line='7A56E0', lw=1.5)
        slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w))
        return h

    slides = c['deck']
    total = len(slides)
    for n, s in enumerate(slides, 1):
        sl = prs.slides.add_slide(blank)
        bg(sl)
        kind = s['kind']
        if kind == 'title':
            sl.shapes.add_picture(str(ASSETS / 'moonlight-team.jpg'), 0, 0, prs.slide_width, prs.slide_height)
            rect(sl, 0, 4.9, 13.333, 2.6, fill=DARK, alpha=72)
            rect(sl, 0.7, 4.98, 2.4, 0.04, fill=LAV)
            text(sl, 0.65, 5.05, 9, 1.0, c['app'], 44, 'FFFFFF', True, western)
            text(sl, 0.65, 5.95, 11.5, 0.9, c['t_deck'] + '  ·  ' + c['tagline'], 16, LAV, False, western, italic=True)
            text(sl, 0.65, 6.75, 9, 0.4, c['version'].format(v=VERSION, d=DATE[lang]) + '  ·  ' + c['team'], 12, 'D9CCFF')
            continue
        if kind == 'closing':
            sl.shapes.add_picture(str(ASSETS / 'moonlight-team.jpg'), 0, 0, prs.slide_width, prs.slide_height)
            rect(sl, 0, 4.4, 13.333, 3.1, fill=DARK, alpha=70)
            text(sl, 0, 4.7, 13.333, 1.4, s['title'], 60, 'FFFFFF', True, western, PP_ALIGN.CENTER)
            text(sl, 0, 5.8, 13.333, 0.8, s['sub'], 28, LAV, False, western, PP_ALIGN.CENTER, italic=True)
            text(sl, 0, 6.75, 13.333, 0.5, '%s  ·  %s' % (c['team'], c['app']), 14, 'D9CCFF', align=PP_ALIGN.CENTER)
            continue
        chrome(sl, n, total)
        heading(sl, s['title'])
        if kind == 'bullets':
            shot = s.get('shot')
            width = 6.0 if shot else 11.8
            y = 1.85
            step = 0.95 if len(s['items']) <= 5 else 0.82
            for it in s['items']:
                rect(sl, 0.7, y + 0.2, 0.16, 0.16, fill=ROSE, shape=MSO_SHAPE.DIAMOND)
                text(sl, 1.05, y, width, step, it, 20 if shot else 22, 'EFE8FF')
                y += step
            if shot:
                picture_frame(sl, ASSETS / 'screens' / ('%s-%s.jpg' % (c['shots_dir'], shot)), 7.35, 1.85, 5.5)
        elif kind == 'cards':
            for i, (h, t) in enumerate(s['cards']):
                x, y = 0.7 + (i % 3) * 4.1, 1.9 + (i // 3) * 2.45
                rect(sl, x, y, 3.8, 2.2, fill=MID, line='7A56E0', shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                text(sl, x + 0.2, y + 0.18, 3.4, 0.6, h, 22, LAV, True, western)
                text(sl, x + 0.2, y + 0.85, 3.4, 1.3, t, 16, 'EFE8FF')
        elif kind == 'diagram':
            sl.shapes.add_picture(str(diagram_png), Inches(0.7), Inches(1.75), Inches(11.9))
        elif kind == 'stats':
            for i, (num, lab) in enumerate(s['stats']):
                x = 0.7 + i * 3.05
                rect(sl, x, 2.2, 2.8, 2.6, fill=MID, line='7A56E0', shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                text(sl, x, 2.6, 2.8, 1.0, fill(num, m), 40, LAV, True, western, PP_ALIGN.CENTER)
                text(sl, x + 0.15, 3.7, 2.5, 1.0, fill(lab, m), 15, 'EFE8FF', align=PP_ALIGN.CENTER)
            text(sl, 0.7, 5.4, 11.9, 0.8, s['note'], 18, 'D9CCFF', italic=True, font=western)
    prs.core_properties.title = '%s - %s' % (c['app'], c['t_deck'])
    prs.core_properties.author = c['team']
    prs.save(str(out))


# ------------------------------------------------------------------------------------------------ main
def main():
    langs = sys.argv[1:] or ['en', 'ko']
    m = measure()
    print('measured:', m)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=EDGE, headless=True)
        for lang in langs:
            c = C[lang]
            outdir = REPORT / lang
            outdir.mkdir(exist_ok=True)
            diagram = ASSETS / ('diagram-%s.png' % lang)
            make_diagram(c, browser, diagram)
            n = NAMES[lang]
            for kind in ('report', 'guide'):
                make_pdf(kind, c, m, lang, browser, outdir / (n[kind] + '.pdf'))
                build_docx(kind, c, m, lang, diagram, outdir / (n[kind] + '.docx'))
            build_pptx(c, m, lang, diagram, outdir / (n['deck'] + '.pptx'))
            print(lang, 'done')
        browser.close()


if __name__ == '__main__':
    main()
