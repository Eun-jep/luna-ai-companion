"""Tests for code he showed her: the program reads the functions and tells her what is worth testing.
A language model writes tests that look right and miss the edges, so the program lists, for every function in his message, what it takes, what
it can raise or return, which branches and loops it has, and the edge cases that follow (empty, None, zero, boundaries, wrong type, the error
path). She writes the tests from that list in the style he names (pytest, unittest, jest; this project's own style if he shows a test file).
Nothing is created or run: the tests appear in the chat, and a file is written only through the edit plate with his press (existing file)."""
import ast
import re

MAX_REPORT = 2400
MAX_FUNCS = 6


def looks_like_python(text):
    return bool(re.search(r'(?m)^\s*(async\s+)?def\s+\w+\s*\(', text or ''))


def looks_like_js(text):
    return bool(re.search(r'(?m)^\s*(export\s+)?(async\s+)?function\s+\w+\s*\(|^\s*(export\s+)?const\s+\w+\s*=\s*(async\s*)?\(?[\w\s,{}=]*\)?\s*=>', text or ''))


def _py_funcs(text):
    m = re.search(r'(?m)^(@|(?:async\s+)?def\s|class\s|import\s|from\s+\w+\s+import)', text)
    lines = text[m.start():].splitlines() if m else []
    tree = None
    for _ in range(3):   # prose around the code: drop what does not parse, from the line the parser stopped at
        try:
            tree = ast.parse('\n'.join(lines))
            break
        except SyntaxError as exc:
            if not exc.lineno or exc.lineno < 2:
                return None
            lines = lines[:exc.lineno - 1]
    if tree is None:
        return None
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('test'):
            args = [a.arg for a in node.args.args if a.arg not in ('self', 'cls')]
            raises, branches, loops, returns = set(), 0, 0, 0
            for n in ast.walk(node):
                if isinstance(n, ast.Raise):
                    exc = n.exc.func if isinstance(n.exc, ast.Call) else n.exc
                    raises.add(ast.unparse(exc) if exc is not None else 'исключение')
                elif isinstance(n, (ast.If, ast.IfExp)):
                    branches += 1
                elif isinstance(n, (ast.For, ast.While, ast.comprehension)):
                    loops += 1
                elif isinstance(n, ast.Return) and n.value is not None:
                    returns += 1
            found.append({'name': node.name, 'args': args, 'defaults': len(node.args.defaults), 'raises': sorted(raises)[:4], 'branches': branches,
                          'loops': loops, 'returns': returns, 'async': isinstance(node, ast.AsyncFunctionDef), 'doc': bool(ast.get_docstring(node)),
                          'method': any(a.arg in ('self', 'cls') for a in node.args.args[:1]), 'line': node.lineno})
    return sorted(found, key=lambda f: f['line'])


def _js_funcs(text):
    found = []
    for m in re.finditer(r'(?m)^\s*(?:export\s+)?(async\s+)?function\s+(\w+)\s*\(([^)]*)\)|^\s*(?:export\s+)?const\s+(\w+)\s*=\s*(async\s*)?\(([^)]*)\)\s*=>', text):
        name = m.group(2) or m.group(4)
        raw = m.group(3) if m.group(2) else m.group(6)
        args = [a.split('=')[0].strip() for a in (raw or '').split(',') if a.strip()]
        body = text[m.end():m.end() + 1500]
        found.append({'name': name, 'args': args, 'defaults': (raw or '').count('='), 'raises': ['throw'] if re.search(r'\bthrow\b', body) else [],
                      'branches': len(re.findall(r'\bif\s*\(|\?[^.?]', body)), 'loops': len(re.findall(r'\b(for|while)\s*\(|\.(map|filter|reduce|forEach)\(', body)),
                      'returns': len(re.findall(r'\breturn\b', body)), 'async': bool(m.group(1) or m.group(5)), 'doc': False, 'method': False,
                      'line': text.count('\n', 0, m.start()) + 1})
    return found


def edges(f):
    """The cases that follow from what the function takes and does."""
    out = []
    for a in f['args'][:4]:
        out.append('«%s»: пустое значение (None/пустая строка/пустой список), ноль или минус, очень большое' % a)
    if f['branches']:
        out.append('каждая ветка условия отдельно (веток: %d) и граница между ними ровно на значении условия' % f['branches'])
    if f['loops']:
        out.append('цикл: ноль элементов, один, много; повторяющиеся элементы')
    for r in f['raises']:
        out.append('ошибка %s: тест, что она поднимается при плохом входе, и что при хорошем её нет' % r)
    if f['defaults']:
        out.append('вызов без необязательных аргументов и с ними')
    if f['async']:
        out.append('асинхронность: дождаться результата, таймаут, отмена')
    if not f['returns']:
        out.append('функция ничего не возвращает: проверяй её побочный эффект (запись, вызов, изменение аргумента)')
    return out[:7]


def analyze(text):
    """The list of what to test next to a message that shows code; '' when there is no code or he did not ask for tests."""
    if not isinstance(text, str) or len(text) < 30:
        return ''
    if not re.search(r'(?i)(тест|test|покрыт|coverage|pytest|unittest|jest|проверк.*функци|테스트|단위 ?검증|テスト|検証)', text):
        return ''
    funcs = None
    lang = ''
    if looks_like_python(text):
        funcs, lang = _py_funcs(text), 'Python'
    if funcs is None and looks_like_js(text):
        funcs, lang = _js_funcs(text), 'JavaScript'
    if not funcs:
        return ''
    out = ['Подготовка тестов программой (%s, она прочитала код; тесты пишет Луна по этому списку, в стиле, который он назвал или который виден из его тестов; '
           'ничего не создаётся и не запускается, готовые тесты она показывает в чате. Не придумывай поведение, которого в коде нет: если неясно, '
           'что функция должна возвращать, спроси.)' % lang]
    for f in funcs[:MAX_FUNCS]:
        sig = '%s(%s)' % (f['name'], ', '.join(f['args']))
        out.append('— %s%s, строка %d: %s' % ('метод ' if f['method'] else '', sig, f['line'], '; '.join(edges(f)) or 'проверь основной сценарий и один сбой'))
    if len(funcs) > MAX_FUNCS:
        out.append('Функций больше, разобраны первые %d.' % MAX_FUNCS)
    out.append('Сначала один тест на обычный случай, потом края из списка; каждый тест проверяет одну вещь и называется тем, что проверяет. '
               'Скажи прямо, что тесты не запускались и их надо прогнать. Если он просит сохранить тесты в файл: новый файл тестов кладёт блок lunaproject '
               'в папку, которую он разрешил (workspace; он увидит файл целиком и нажмёт «Применить», откат в Журнале), существующий файл так не перезаписать; '
               'если папка проекта не разрешена, скажи об этом и дай готовый код в чате.')
    return '\n'.join(out)[:MAX_REPORT]
