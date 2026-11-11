"""Exact table summaries: the program computes sums, averages, gaps, duplicates over the whole file; she quotes them."""
import os
import sys, tempfile, pathlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.skills import tables as T
from luna.hands import docfiles
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

ok('numbers in several formats', T.number('1 234,50') == 1234.5 and T.number('1,234.50') == 1234.5 and T.number('12%') == 12.0 and T.number('$5') == 5.0 and T.number(3) == 3.0)
ok('text and bool are not numbers', T.number('abc') is None and T.number('') is None and T.number(True) is None and T.number('1.2.3') is None)
ok('dates', str(T.when('2024-05-17')) == '2024-05-17' and str(T.when('17.05.2024')) == '2024-05-17' and T.when('2024-13-40') is None and T.when('x') is None)

tmp = pathlib.Path(tempfile.mkdtemp())
rows = ['Дата;Менеджер;Сумма;Комментарий']
for i in range(1, 1001):   # 1000 rows: far more than fits in the text
    rows.append('2024-01-%02d;%s;%s;' % (i % 28 + 1, 'Анна' if i % 4 else 'Борис', '%d,50' % i))
rows.append('2024-01-05;Анна;100,50;')
rows.append('2024-01-05;Анна;100,50;')   # a duplicate row
(tmp / 'sales.csv').write_text('\n'.join(rows), encoding='utf-8')
d = T.digest(tmp / 'sales.csv')
total = sum(i + 0.5 for i in range(1, 1001)) + 201.0
ok('rows and columns counted over the whole file', 'строк данных: 1002, колонок: 4' in d)
ok('the sum is exact', '«Сумма»: числа, 1002 значений, сумма %s' % T._fmt(total) in d)
ok('min and max', 'минимум 1.5' in d and 'максимум 1 000.5' in d)
ok('dates range', 'даты, от 2024-01-01 до 2024-01-28' in d)
ok('text column: top values with counts', 'Анна: 752' in d and 'Борис: 250' in d)
ok('empty column and duplicates are named', 'пусто' in d and 'одинаковых строк: 1' in d)
ok('the summary says whose numbers these are', 'посчитана программой' in d)

(tmp / 'plain.csv').write_text('1,2\n3,4\n', encoding='utf-8')
ok('no header: columns are numbered', 'колонка 1' in T.digest(tmp / 'plain.csv') and 'сумма 4' in T.digest(tmp / 'plain.csv'))
(tmp / 'a.txt').write_text('hi', encoding='utf-8')
ok('not a table: nothing', T.digest(tmp / 'a.txt') == '')
(tmp / 'e.csv').write_text('', encoding='utf-8')
ok('an empty file: nothing, no crash', T.digest(tmp / 'e.csv') == '')
(tmp / 'mixed.csv').write_text('x\n1\n2\nabc\n4\n5\n6\n7\n8\n9\n10\n', encoding='utf-8')
ok('a stray text cell is counted, not hidden', 'не число: 1' in T.digest(tmp / 'mixed.csv'))

try:
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Q1'
    ws.append(['Товар', 'Кол-во', 'Цена']); [ws.append(['A', i, 2.5]) for i in range(1, 101)]
    wb.create_sheet('Q2').append(['Имя', 'Возраст']); wb['Q2'].append(['Ли', 30])
    wb.save(tmp / 'book.xlsx')
    x = T.digest(tmp / 'book.xlsx')
    ok('excel: each sheet has its own summary', 'Лист «Q1»' in x and 'Лист «Q2»' in x and 'сумма 5 050' in x and 'сумма 250' in x)
except ImportError:
    ok('excel skipped (openpyxl is not installed)', True)

# through the reading path
docfiles.ROOTS = [tmp]
docfiles.PENDING['t'] = {'kind': 'file', 'path': str(tmp / 'sales.csv'), 't': 9e18}
shown = docfiles.read('t')
ok('reading a table appends the exact summary', 'СВОДКА' in shown['text'] and 'строк данных: 1002' in shown['text'])
docfiles.PENDING['u'] = {'kind': 'file', 'path': str(tmp / 'a.txt'), 't': 9e18}
ok('reading a text file is unchanged', docfiles.read('u')['text'] == 'hi')
