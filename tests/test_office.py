import os
import sys, json, tempfile, pathlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import office
office.FOLDER = pathlib.Path(tempfile.mkdtemp()) / 'Luna'
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

docx = {'type': 'docx', 'title': 'Отчёт: продажи/Q3?', 'subtitle': 'Для руководителя', 'blocks': [
    {'h': 1, 'text': 'Итоги'}, {'p': 'Выручка выросла на **12%**, а *расходы* остались прежними.'},
    {'ul': ['Первый пункт', 'Второй']}, {'ol': ['Шаг один', 'Шаг два']},
    {'table': {'header': ['Месяц', 'Выручка'], 'rows': [['Июль', '100'], ['Август', '120']]}}, {'pagebreak': True}, {'h': 2, 'text': 'Вывод'}, {'p': 'Всё хорошо.'}]}
pptx = {'type': 'pptx', 'title': 'Презентация', 'accent': '#D43B6F', 'slides': [
    {'layout': 'title', 'title': 'Квартальный отчёт', 'subtitle': 'Луна и команда'},
    {'title': 'Главное', 'bullets': ['Рост 12%', 'Новые клиенты: 40', 'Риски под контролем'], 'notes': 'Говорить спокойно'},
    {'title': 'Цифры', 'table': {'header': ['Месяц', 'Выручка'], 'rows': [['Июль', '100'], ['Август', '120']]}},
    {'title': 'Итог', 'text': 'Спасибо за внимание.'}]}
xlsx = {'type': 'xlsx', 'title': 'Бюджет', 'sheets': [{'name': 'Q3', 'header': ['Месяц', 'Доход', 'Расход'], 'rows': [
    ['Июль', 100, 60], ['Август', 120, 70], ['Итого', '=SUM(B2:B3)', '=SUM(C2:C3)'], ['=cmd|calc', '=HYPERLINK("http://x","y")', '=Other!A1']],
    'chart': {'type': 'bar', 'title': 'Доход и расход', 'values': [2, 3]}}]}

made = {}
for spec in (docx, pptx, xlsx):
    plate = office.propose(json.dumps(spec, ensure_ascii=False))
    ok('plate for ' + spec['type'], plate and plate['app'] and plate['name'].endswith(spec['type']))
    r = office.make(plate['token'])
    p = pathlib.Path(r['folder']) / r['name']
    made[spec['type']] = p
    ok('file created ' + r['name'], p.is_file() and p.stat().st_size > 2000)
    try: office.make(plate['token']); ok('replay refused', False)
    except PermissionError: ok('replay refused', True)

# round-trip: read them back with the libraries
import docx as D, pptx as P, openpyxl as X
d = D.Document(str(made['docx']))
ok('docx has headings, table, bold run', any(p.style.name.startswith('Heading') for p in d.paragraphs) and len(d.tables) == 1 and any(r.bold for p in d.paragraphs for r in p.runs))
pr = P.Presentation(str(made['pptx']))
ok('pptx 4 slides + notes', len(pr.slides) == 4 and pr.slides[1].notes_slide.notes_text_frame.text == 'Говорить спокойно')
wb = X.load_workbook(str(made['xlsx']))
ws = wb['Q3']
ok('xlsx formula kept, chart added', ws['B4'].value == '=SUM(B2:B3)' and len(ws._charts) == 1)
ok('hostile formulas stay text', all(ws.cell(5, c).data_type == 's' for c in (1, 2, 3)))

# second file with the same name never overwrites
plate = office.propose(json.dumps(docx, ensure_ascii=False)); r = office.make(plate['token'])
ok('no overwrite: "(2)"', '(2)' in r['name'])
ok('only inside the Luna folder', all(p.parent == office.FOLDER for p in made.values()))

# hostile / broken specs are refused
bad = [{'type': 'exe', 'title': 'x'}, {'type': 'docx', 'title': '..\\..\\evil', 'blocks': [{'p': 'a'}]},
       {'type': 'docx', 'blocks': [{'script': 'x'}]}, {'type': 'docx', 'blocks': []}, {'type': 'pptx', 'slides': [{'title': 'x', 'bullets': ['a'] * 9}]},
       {'type': 'xlsx', 'sheets': [{'rows': [[1]], 'chart': {'type': 'bar', 'values': [99]}}]}, {'type': 'pptx', 'accent': 'red', 'slides': [{'title': 'x'}]},
       {'type': 'docx', 'blocks': [{'h': 9, 'text': 'x'}]}, {'type': 'docx', 'blocks': [{'p': 'x'}] * 400}]
res = [office.propose(json.dumps(b)) for b in bad]
print('hostile specs ->', [bool(x) for x in res])
ok('all but the harmless one refused (the "..\\\\evil" title is only sanitised)', [bool(x) for x in res] == [False, True, False, False, False, False, False, False, False])
plate = office.propose(json.dumps(bad[1])); r = office.make(plate['token'])
ok('path traversal in title neutralised', pathlib.Path(r['folder']) == office.FOLDER and '..' not in r['name'] and '\\' not in r['name'])
ok('garbage text -> None', office.propose('not json') is None and office.propose('[]') is None)
ok('reserved name', office._safe_name('CON').startswith('_'))
print('folder:', office.FOLDER, sorted(p.name for p in office.FOLDER.iterdir()))
