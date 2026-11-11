"""A read-only look into a project's SQLite file: only one read, only on his press, nothing is ever written (sqlrun.py + /sql/run)."""
import os
import sys, json, sqlite3, tempfile, pathlib, threading, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.dev import sqlrun
from luna.hands import runner
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

root = pathlib.Path(tempfile.mkdtemp())
db = root / 'shop.db'
con = sqlite3.connect(db)
con.execute('create table users (id integer primary key, name text, password text, note text)')
con.executemany('insert into users (name, password, note) values (?, ?, ?)', [('u%d' % i, 'hunter%d' % i, 'token=abc123secretvalue' if i == 3 else 'ok') for i in range(60)])
con.commit(); con.close()
runner.project_dir = lambda: root

p = sqlrun.propose('select id, name, password, note from users order by id')
ok('plate: token, file and the exact query', p and p['db'] == 'shop.db' and p['sql'].startswith('select id') and len(p['token']) == 16)
r = sqlrun.run(p['token'])
ok('result: rows limited, cut flagged', r['rows'] == sqlrun.MAX_ROWS and r['cut'])
ok('secret-looking column is hidden', 'hunter' not in r['text'] and '***' in r['text'])
ok('a secret inside a value is masked', 'abc123secretvalue' not in r['text'])
ok('header with column names', r['text'].splitlines()[0] == 'id | name | password | note')
try:
    sqlrun.run(p['token']); ok('token is single use', False)
except PermissionError:
    ok('token is single use', True)
p = sqlrun.propose('select 1')
sqlrun.PENDING[p['token']] = (sqlrun.PENDING[p['token']][0], 'select 1', time.time() - 500)
try:
    sqlrun.run(p['token']); ok('an old plate expires', False)
except PermissionError:
    ok('an old plate expires', True)

for bad, code in [('delete from users', 'notread'), ('drop table users', 'notread'), ('update users set name = 1', 'notread'), ('insert into users (name) values (1)', 'notread'),
                  ('select 1; select 2', 'many'), ('pragma table_info(users)', 'notread'), ('with x as (select 1) delete from users', 'notread'), ('', None)]:
    got = sqlrun.propose(bad)
    ok('refused: %r' % bad, got is None if code is None else got == {'fail': code})
ok('attach is refused', (sqlrun.propose("attach database 'x.db' as x") or {}).get('fail') in ('empty', 'notread'))
ok('replace() inside a select is fine', sqlrun.propose("select replace(name, 'u', 'x') from users")['sql'].startswith('select replace'))
ok('explain is a read', 'token' in sqlrun.propose('explain query plan select * from users'))

# even a write that slipped past the text check cannot write
sqlrun.PENDING['t1'] = (str(db), 'delete from users', time.time())
try:
    sqlrun.run('t1'); ok('write refused by the database itself', False)
except RuntimeError as exc:
    ok('write refused by the database itself', str(exc).startswith('badquery'))
con = sqlite3.connect(db); n = con.execute('select count(*) from users').fetchone()[0]; con.close()
ok('nothing was written', n == 60)

old = sqlrun.SECONDS
sqlrun.SECONDS = 0.3
sqlrun.PENDING['t2'] = (str(db), 'with recursive c(x) as (select 1 union all select x+1 from c) select count(*) from c', time.time())
try:
    t0 = time.time(); sqlrun.run('t2'); ok('a long query is stopped', False)
except RuntimeError as exc:
    ok('a long query is stopped', str(exc) == 'timeout' and time.time() - t0 < 5)
sqlrun.SECONDS = old

sqlrun.PENDING['t3'] = (str(db), 'select nosuch from users', time.time())
try:
    sqlrun.run('t3')
except RuntimeError as exc:
    ok('a bad query: the database error is returned', str(exc).startswith('badquery:') and 'nosuch' in str(exc))

# several databases: the name decides
(root / 'data').mkdir(); sqlite3.connect(root / 'data' / 'log.sqlite').close()
w = sqlrun.propose('select 1')
ok('several databases: she must name one', w == {'fail': 'whichdb', 'names': w.get('names')} and set(w['names']) == {'shop.db', 'log.sqlite'})
ok('named database is used', sqlrun.propose('log.sqlite >> select 1')['db'] == 'log.sqlite')
ok('unknown name: no database', sqlrun.propose('nope.db >> select 1') == {'fail': 'nodb'})
runner.project_dir = lambda: None
ok('no project shown: nothing', sqlrun.propose('select 1') == {'fail': 'noproject'})
runner.project_dir = lambda: pathlib.Path(tempfile.mkdtemp())
ok('no database in the project', sqlrun.propose('select 1') == {'fail': 'nodb'})

# over HTTP
import app
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 8899), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(path, d):
    rq = urllib.request.Request('http://127.0.0.1:8899' + path, json.dumps(d).encode(), {'Content-Type': 'application/json', 'X-App-Token': app.TOKEN})
    try:
        with urllib.request.urlopen(rq) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
runner.project_dir = lambda: root
os.remove(root / 'data' / 'log.sqlite')
p = sqlrun.propose('select count(*) as n from users')
st, body = post('/sql/run', {'token': p['token']})
ok('http: the press returns the result', st == 200 and body['text'] == 'n\n60' and body['rows'] == 1)
st, body = post('/sql/run', {'token': p['token']})
ok('http: the same press twice is refused', st == 403)
st, body = post('/sql/run', {'token': 5})
ok('http: a wrong token type is refused', st in (400, 403))
