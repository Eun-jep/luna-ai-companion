"""IT helpers: service logs to the cause (logs.py), SQL checks (sqlcheck.py), test planning (testgen.py), and their hook in work mode. Nothing is executed."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logs, sqlcheck, testgen
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

LOG = '''2025-03-01 10:00:01 INFO  service starting
2025-03-01 10:00:02 INFO  config loaded
2025-03-01 10:00:03 WARN  pool size 5 is low for 20 workers
2025-03-01 10:00:09 ERROR could not connect to db 10.0.0.5:5432: Connection refused
2025-03-01 10:00:10 ERROR request 101 failed: no connection
2025-03-01 10:00:11 ERROR request 102 failed: no connection
2025-03-01 10:00:12 ERROR request 103 failed: no connection
2025-03-01 10:00:13 ERROR request 104 failed: no connection
2025-03-01 10:00:14 FATAL shutting down password=hunter2
'''
r = logs.analyze(LOG)
ok('log: recognised', logs.looks_like_log(LOG) and r != '')
ok('log: first problem is the db connection, not the loud echo', 'строка 4' in r and 'could not connect' in r)
ok('log: the warning before it is named', 'pool size 5' in r)
ok('log: repeated echoes counted as consequence', '5×' in r or '4×' in r)
ok('log: usual cause for refused connection', 'соединение отказано' in r)
ok('log: secrets masked', 'hunter2' not in r)
ok('log: time span', '10:00:01' in r and '10:00:14' in r)
ok('log: nothing run is promised', 'ничего не запускала' in r)
ok('plain text is not a log', logs.analyze('привет, как дела?\nвсё хорошо\n') == '')
ok('too short is not a log', logs.analyze('2025-03-01 10:00:01 ERROR x\n2025-03-01 10:00:02 INFO y') == '')
clean = '\n'.join('2025-03-01 10:00:%02d INFO ok %d' % (i, i) for i in range(10))
ok('clean log: says no errors and asks for earlier part', 'Ошибок и явных сбоев' in logs.analyze(clean))
oom = '\n'.join(['Mar  1 10:00:%02d host app[1]: running' % i for i in range(6)] + ['Mar  1 10:01:00 host kernel: Out of memory: Killed process 77 (app)'])
ok('log without levels: OOM found', 'OOM' in logs.analyze(oom))

# SQL
ok('delete without where is dangerous', 'опасно' in sqlcheck.analyze('DELETE FROM users;') and 'ВСЕ строки' in sqlcheck.analyze('DELETE FROM users;'))
ok('delete with where is calm', 'опасно' not in sqlcheck.analyze("DELETE FROM users WHERE id = 5;"))
ok('update without where', 'UPDATE без WHERE' in sqlcheck.analyze("UPDATE users SET admin = 1"))
ok('drop table warned', 'DROP' in sqlcheck.analyze('drop table orders;') and 'копия' in sqlcheck.analyze('drop table orders;'))
ok('= NULL flagged', 'IS NULL' in sqlcheck.analyze('SELECT id FROM t WHERE x = NULL'))
ok('nullable column is not NULL', 'IS NULL' not in sqlcheck.analyze('SELECT id FROM t WHERE x = nullable_col'))
ok('implicit cross join', 'декартово' in sqlcheck.analyze('SELECT a.id FROM a, b'))
ok('join without on', 'JOIN без ON' in sqlcheck.analyze('SELECT a.id FROM a JOIN b'))
ok('leading percent like', 'LIKE' in sqlcheck.analyze("SELECT id FROM t WHERE name LIKE '%abc'"))
ok('function on column', 'индекс' in sqlcheck.analyze("SELECT id FROM t WHERE date(created) = '2025-01-01'"))
ok('not in subquery', 'NOT EXISTS' in sqlcheck.analyze('SELECT id FROM t WHERE id NOT IN (SELECT id FROM u)'))
ok('keywords inside strings and comments do not trigger', 'опасно' not in sqlcheck.analyze("SELECT 'delete from x' FROM t WHERE id=1 -- DROP TABLE t"))
ok('kinds: read and write', 'чтение' in sqlcheck.analyze('SELECT id FROM t WHERE id=1') and 'запись' in sqlcheck.analyze('INSERT INTO t (a) VALUES (1)'))
ok('dangerous goes first in the instructions', 'ПЕРВЫМ' in sqlcheck.analyze('DELETE FROM t'))
ok('says it ran nothing', 'ничего не выполняла' in sqlcheck.analyze('SELECT 1 FROM t WHERE a=1'))
ok('not sql: plain chat', sqlcheck.analyze('давай выберем фильм и удалим лишнее') == '')
ok('insert without column list', 'списка колонок' in sqlcheck.analyze("INSERT INTO t VALUES (1, 2)"))

# tests planning
CODE = '''тесты напиши, пожалуйста
def split_bill(total, people, tip=0):
    if people <= 0:
        raise ValueError("people")
    return [round((total + tip) / people, 2) for _ in range(people)]
'''
r = testgen.analyze(CODE)
ok('testgen: function and arguments listed', 'split_bill(total, people, tip)' in r)
ok('testgen: raise path is a case', 'ValueError' in r)
ok('testgen: branch and default cases', 'ветк' in r and 'необязательных' in r)
ok('testgen: honest that nothing ran', 'не запускались' in r and 'ничего не создаётся' in r)
ok('testgen: no ask for tests, no list', testgen.analyze('def f(x):\n    return x + 1\n  # просто посмотри') == '')
ok('testgen: no code, no list', testgen.analyze('напиши тесты для чего-нибудь пожалуйста') == '')
JS = 'write tests\nexport function clamp(x, lo = 0, hi = 10) {\n  if (x < lo) return lo;\n  if (x > hi) throw new Error("hi");\n  return x;\n}\n'
r = testgen.analyze(JS)
ok('testgen: javascript function', 'clamp(x, lo, hi)' in r and 'Error' in r or 'throw' in r)
ok('testgen: broken python falls back quietly', testgen.analyze('write tests\ndef broken(:\n  pass\n') == '')
many = 'тесты\n' + '\n'.join('def f%d(a):\n    return a\n' % i for i in range(9))
ok('testgen: capped list', testgen.analyze(many).count('— f') == testgen.MAX_FUNCS and 'Функций больше' in testgen.analyze(many))

# the hook in app.py: only in work mode, next to his message
import tempfile, pathlib, threading, json, urllib.request, urllib.error
import app, character
character.MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'; app.load_memory()
seen = {}
def fake(m, model=None, vision=False, max_tokens=800, **kw):
    seen['last'] = m[-1]['content'] if isinstance(m[-1]['content'], str) else m[-1]['content'][-1]['text']
    yield 'ок'
app.generate_stream = fake
app.generate = lambda m: 'не умею'
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8803), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(d):
    r = urllib.request.Request('http://127.0.0.1:8803/chat', json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    with urllib.request.urlopen(r) as x: return x.status, x.read()
post({'message': 'почему сервис упал?\n' + LOG, 'lang': 'ru', 'agent': True, 'work': True})
ok('work mode: the log reading sits next to the message', 'Разбор лога программой' in seen['last'] and 'Первая проблема' in seen['last'])
post({'message': 'почему сервис упал?\n' + LOG, 'lang': 'ru', 'agent': True, 'work': False})
ok('no work mode: no reading', 'Разбор лога программой' not in seen['last'])
post({'message': 'что делает этот запрос?\nDELETE FROM users;', 'lang': 'ru', 'agent': True, 'work': True})
ok('work mode: SQL reading', 'Разбор SQL программой' in seen['last'] and 'ВСЕ строки' in seen['last'])
post({'message': CODE, 'lang': 'ru', 'agent': True, 'work': True})
ok('work mode: test planning', 'Подготовка тестов программой' in seen['last'])
ok('testgen: how to save into a file (new file only, with his press)', 'lunaproject' in testgen.analyze(CODE) and 'нажмёт «Применить»' in testgen.analyze(CODE) and 'не перезаписать' in testgen.analyze(CODE))
