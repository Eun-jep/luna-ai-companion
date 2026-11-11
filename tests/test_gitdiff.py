"""Git change review: the diff is parsed and checked by the program; secrets are never printed; git runs read-only on a real temporary repository."""
import os
import sys, tempfile, pathlib, subprocess, shutil, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.dev import gitdiff as G
from luna.dev import devtools
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

ok('scopes', G.scope_args('')[0] == 'working' and G.scope_args('staged')[0] == 'staged' and G.scope_args('last')[0] == 'last'
   and G.scope_args('main')[0] == 'branch' and G.scope_args('branch feature/x-1')[0] == 'branch')
ok('hostile refs are refused', all(G.scope_args(x) is None for x in ('--output=x', '-x', 'a..b', 'a b;c', '$(id)', 'x' * 80, 'main/', 'a.lock')))

KEY = 'AKIA' + 'ABCDEFGHIJKLMNOP'
PW = 'hunter2hunter2xx'
DIFF = '\n'.join([
    'diff --git a/app/main.py b/app/main.py', 'index 1..2 100644', '--- a/app/main.py', '+++ b/app/main.py', '@@ -1,3 +1,8 @@',
    ' import os', '+AWS = "%s"' % KEY, '+password = "%s"' % PW, '+import pdb', '+subprocess.run(cmd, shell=True)', ' x = 1', '-y = 2', '+# TODO later',
    'diff --git a/tests/test_a.py b/tests/test_a.py', 'index 1..2 100644', '--- a/tests/test_a.py', '+++ b/tests/test_a.py', '@@ -1,6 +1,2 @@',
    '-def test_one():', '-    pass', '-def test_two():', '-    pass', '+@pytest.mark.skip',
    'diff --git a/package.json b/package.json', '--- a/package.json', '+++ b/package.json', '@@ -1 +1,2 @@', '+"x": 1',
    'diff --git a/web/app.js b/web/app.js', '--- a/web/app.js', '+++ b/web/app.js', '@@ -10,0 +11,3 @@', '+<<<<<<< HEAD', '+console.log(1)', '+el.innerHTML = a',
    'diff --git a/db/migrations/001.sql b/db/migrations/001.sql', 'new file mode 100644', '--- /dev/null', '+++ b/db/migrations/001.sql', '@@ -0,0 +1 @@', '+ALTER TABLE t;',
    'diff --git a/.env b/.env', 'new file mode 100644', '--- /dev/null', '+++ b/.env', '@@ -0,0 +1 @@', '+SECRET=%s' % PW,
    'diff --git a/img.png b/img.png', 'new file mode 100644', 'Binary files /dev/null and b/img.png differ', ''])
files = G.parse(DIFF)
by = {f['path']: f for f in files}
ok('files, statuses and counts', len(files) == 7 and by['app/main.py']['add'] == 5 and by['app/main.py']['del'] == 1 and by['db/migrations/001.sql']['status'] == 'added' and by['img.png']['binary'])
ok('new line numbers follow the hunk header', ('app/main.py', 2) in [(f['path'], n) for f in files for n, k, t in f['lines'] if k == '+' and 'AWS' in t])
found = G.findings(files)
text = ' '.join('%s:%s:%s' % (p, ln, w) for _, p, ln, w in found)
ok('a key in an added line is found by place', 'app/main.py:2:секрет в изменении: AWS access key' in text)
ok('a password assignment in an added line is found', 'app/main.py:3:секрет в изменении: пароль/ключ в коде' in text)
ok('shell=True, forgotten debugging', 'app/main.py:5:shell=True' in text and 'app/main.py:4:забытая отладка' in text)
ok('a merge conflict marker and innerHTML in js', 'web/app.js:11:остался маркер' in text and 'web/app.js:13:innerHTML' in text and 'web/app.js:12:забытая отладка' in text)
ok('a skipped test', 'tests/test_a.py' in text and 'отключён' in text)
notes = G.structure(files)
ok('tests removed', any('тестов удалено больше' in n for n in notes))
ok('manifest without a lock file', any('package.json' in n and 'lock' in n for n in notes))
ok('migration is flagged', any('миграция БД db/migrations/001.sql' in n for n in notes))
r = G.report(files, 'проверка')
ok('the report never contains a secret value', KEY not in r and PW not in r)
ok('secret files and binaries have no body', '### .env: без тела' in r and '### img.png: без тела' in r)
ok('risky files come first in the diff text', r.index('### app/main.py') < r.index('### package.json'))
ok('the report fits a message', len(r) < 20000 and r.count('\n') > 20)
ok('removed lines are not judged', 'y = 2' not in ' '.join(w for *_, w in found))

# a real repository
if shutil.which('git'):
    repo = pathlib.Path(tempfile.mkdtemp()) / 'repo'; repo.mkdir()
    def git(*a):
        return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false'] + list(a), cwd=repo, capture_output=True, text=True)
    git('init', '-q'); git('checkout', '-q', '-b', 'main')
    (repo / 'a.py').write_text('x = 1\n'); git('add', '.'); git('commit', '-q', '-m', 'base')
    git('checkout', '-q', '-b', 'feature')
    (repo / 'a.py').write_text('x = 1\nimport pdb\n'); git('add', '.'); git('commit', '-q', '-m', 'add pdb ' + 'password=%s' % PW)
    (repo / 'a.py').write_text('x = 1\nimport pdb\nprint(eval("1"))\n')
    (repo / 'new.txt').write_text('fresh\n')
    devtools.GRANTED['a.py'] = {'path': str(repo / 'a.py'), 't': 9e21}
    plate = G.propose('working')
    ok('a plate names the project and the scope', plate['project'] == 'repo' and 'рабочие' in plate['scope'])
    out = G.run(plate['token'])['text']
    ok('working changes are found, untracked files are mentioned', 'a.py' in out and 'eval/exec' in out and 'Неотслеживаемых новых файлов: 1' in out)
    p2 = G.propose('last'); last = G.run(p2['token'])['text']
    ok('the last commit is reviewed, a secret in its message is masked', 'забытая отладка' in last and PW not in last and 'Коммит:' in last)
    p3 = G.propose('main'); br = G.run(p3['token'])['text']
    ok('a branch is compared with the base', 'изменения этой ветки относительно main' in br and 'a.py' in br)
    p4 = G.propose('nosuchbranch')
    try:
        G.run(p4['token']); code = ''
    except RuntimeError as e:
        code = str(e)
    ok('an unknown branch is named', code == 'badref')
    git('add', '-A'); git('commit', '-q', '-m', 'all')
    p5 = G.propose('working')
    try:
        G.run(p5['token']); code = ''
    except RuntimeError as e:
        code = str(e)
    ok('nothing to review is said plainly', code == 'empty')
    p6 = G.propose('staged')
    (repo / 'b.py').write_text('y = 2\n'); git('add', 'b.py')
    ok('staged changes are separate', 'b.py' in G.run(p6['token'])['text'])
    try:
        G.run(p6['token']); again = False
    except PermissionError:
        again = True
    ok('the press works once (real)', again)
    plain = pathlib.Path(tempfile.mkdtemp()) / 'plain'; plain.mkdir(); (plain / 'f.py').write_text('1\n')
    devtools.GRANTED['f.py'] = {'path': str(plain / 'f.py'), 't': 9e22}
    p7 = G.propose('working')
    try:
        G.run(p7['token']); code = ''
    except RuntimeError as e:
        code = str(e)
    ok('a folder outside a repository is said plainly', code == 'norepo')
else:
    ok('git is not installed: real-repository checks skipped', True)
devtools.GRANTED.clear()
ok('no project known: said plainly', G.propose('working') in ({'fail': 'noproject'}, {'fail': 'nogit'}))
