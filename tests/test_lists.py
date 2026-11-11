"""His shopping and to-do lists (lists.py): asked for in words in ru, en, ko and ja, kept in a file, read back; a whole list is never wiped by her.
The test works on a temporary file: his real lists.json is never touched."""
import os
import sys
import tempfile
import pathlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.skills import lists
lists.FILE = pathlib.Path(tempfile.mkdtemp()) / 'lists.json'
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

ADD = [('добавь молоко и хлеб в список покупок', 'shop', ['молоко', 'хлеб']), ('добавь в список дел: позвонить маме', 'todo', ['позвонить маме']),
       ('add milk, eggs to my shopping list', 'shop', ['milk', 'eggs']), ('add to my todo list: call dentist', 'todo', ['call dentist']),
       ('장보기 목록에 우유 추가해줘', 'shop', ['우유']), ('우유를 장보기 목록에 추가해줘', 'shop', ['우유']),
       ('買い物リストに牛乳を追加して', 'shop', ['牛乳']), ('牛乳を買い物リストに追加して', 'shop', ['牛乳'])]
for text, kind, items in ADD:
    ok('add: ' + text, lists.parse(text) == ('add', kind, items))
for text, kind in [('убери молоко из списка покупок', 'shop'), ('remove milk from my shopping list', 'shop'), ('우유를 장보기 목록에서 빼줘', 'shop'), ('牛乳を買い物リストから消して', 'shop')]:
    ok('remove: ' + text, lists.parse(text) and lists.parse(text)[0] == 'del' and lists.parse(text)[1] == kind)
for text, kind in [('что в списке покупок', 'shop'), ('покажи список дел', 'todo'), ('show my shopping list', 'shop'), ('장보기 목록 보여줘', 'shop'), ('買い物リストを見せて', 'shop')]:
    ok('show: ' + text, lists.parse(text) == ('show', kind, []))
for text in ['очисти список покупок', 'clear my shopping list', '장보기 목록 전부 지워줘', '買い物リストを全部消して']:
    ok('wipe is recognised (and refused below): ' + text, lists.parse(text) and lists.parse(text)[0] == 'wipe')
for text in ['какая погода', 'мы вчера ходили в магазин', 'add 5 to 6', 'расскажи про список литературы', 'what is on my mind', 'I put it on the table', '오늘 날씨 어때', '今日は何をしたの', '']:
    ok('plain chat is not a list request: ' + text, lists.parse(text) is None and lists.handle(text) == '')

# the real effect, on the temporary file
hint = lists.handle('добавь молоко и хлеб в список покупок')
ok('added and told to her', 'молоко; хлеб' in hint and lists.load()['shop'] == ['молоко', 'хлеб'])
hint = lists.handle('add Milk to my shopping list')
ok('a duplicate is not added twice', lists.load()['shop'] == ['молоко', 'хлеб', 'Milk'] or 'Уже было' in hint)
hint = lists.handle('добавь молоко в список покупок')
ok('the same item again: said so, kept once', 'Уже было' in hint and lists.load()['shop'].count('молоко') == 1)
lists.handle('買い物リストに牛乳を追加して')
lists.handle('add to my todo list: call dentist')
data = lists.load()
ok('two lists are kept apart', '牛乳' in data['shop'] and data['todo'] == ['call dentist'])
hint = lists.handle('что в списке покупок')
ok('read back in order', '1) молоко' in hint and '牛乳' in hint)
hint = lists.handle('убери хлеб из списка покупок')
ok('removed one item', 'хлеб' in hint and 'хлеб' not in lists.load()['shop'])
hint = lists.handle('убери сыр из списка покупок')
ok('a missing item is said, nothing else changes', 'нет' in hint and 'молоко' in lists.load()['shop'])
before = lists.load()
hint = lists.handle('очисти список покупок')
ok('a whole list is not wiped by her', lists.load() == before and 'не стираешь' in hint)
hint = lists.handle('покажи список дел')
ok('to-do list read', 'call dentist' in hint)

# limits and a broken file
lists.handle('add ' + ', '.join('item%d' % i for i in range(30)) + ' to my shopping list')
ok('at most 8 items in one request', len(lists.load()['shop']) <= 5 + 8 + 1)
lists.FILE.write_text('not json', encoding='utf-8')
ok('a broken file is an empty list, not a crash', lists.load() == {'shop': [], 'todo': []})
lists.FILE.write_text('{"shop": ["a", 5, null, "b"], "todo": "x"}', encoding='utf-8')
ok('odd content is cleaned', lists.load() == {'shop': ['a', 'b'], 'todo': []})
ok('the real file is never the test file', pathlib.Path(lists.__file__).resolve().parent / 'lists.json' != lists.FILE)

# the chat route adds the hint, and not after text from the internet
import app
src = ''.join(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), *f), encoding='utf-8').read() for f in (('app.py',), ('luna', 'server', 'chat.py'), ('luna', 'server', 'hands.py'), ('luna', 'core', 'prompts.py')))
ok('chat route wired, never after web text', "hint += lists.handle(text)" in src and "data.get('web')" in src[src.index('hint += lists.handle(text)') - 200:src.index('hint += lists.handle(text)')])
