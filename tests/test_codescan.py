"""The project audit: the program measures; secrets are reported by place only; risky calls, broken files, Docker/CI/dependency problems are found."""
import os
import sys, tempfile, pathlib, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.dev import codescan as C
from luna.dev import devtools
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

root = pathlib.Path(tempfile.mkdtemp()) / 'shop'
def put(rel, text):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding='utf-8')
KEY = 'AKIA' + 'ABCDEFGHIJKLMNOP'
PW = 'hunter2hunter2xx'
put('app/main.py', 'import subprocess, hashlib\nAWS = "%s"\npassword = "%s"\n\ndef run(cmd, q):\n    subprocess.run(cmd, shell=True)\n    db.execute("select * from t where a=" + q)\n    return eval(q)\n\n'
    'def deep(x):\n' % (KEY, PW) + ''.join('    if x == %d:\n        return %d\n' % (i, i) for i in range(12)) + '    # TODO fix\n    return hashlib.md5(b"x").hexdigest()\n')
put('app/broken.py', 'def oops(:\n    pass\n')
put('web/page.js', 'el.innerHTML = user;\nconst a = process.env.TOKEN;\nconst token = "changeme-please";\n')
put('Dockerfile', 'FROM python:latest\nRUN curl https://x.sh | sh\nCOPY . .\n')
put('.github/workflows/ci.yml', 'on: pull_request_target\njobs:\n  b:\n    steps:\n      - uses: actions/checkout@main\n')
put('requirements.txt', 'flask\nrequests==2.31.0\n')
put('package.json', '{"dependencies": {"left-pad": "*", "ok": "^1.0.0"}, "devDependencies": {}}')
put('.env', 'SECRET=%s\n' % PW)
put('.env.example', 'SECRET=your_secret_here\n')
put('tests/test_app.py', 'password = "%s"\n\ndef test_x():\n    assert True\n' % PW)
put('node_modules/pkg/index.js', 'eval("x")\n')
r = C.scan(str(root))
ok('languages are counted', 'Python: 3 файлов' in r and 'JavaScript: 1 файлов' in r)
ok('an AWS key is found by place, the value is never printed', 'app/main.py:2, AWS access key' in r and KEY not in r)
ok('a password assignment is found and its value is never printed', 'app/main.py:3, пароль/ключ в коде' in r and PW not in r)
ok('placeholders and env reads are not secrets', 'page.js' not in r.split('РИСКИ')[0])
ok('test files do not raise password alarms', 'tests/test_app.py:1' not in r)
ok('a .env file is named, never read, and the example is fine', '.env' in r and 'содержимое не читалось' in r and '.env.example' not in r)
ok('shell=True, eval and SQL from strings are high risks', all(w in r for w in ('app/main.py:6', 'shell=True', 'SQL built from strings', 'eval/exec on data')))
ok('weak hash and innerHTML are found', 'weak hash' in r and 'web/page.js:1' in r)
ok('a Python file that does not parse is listed', 'app/broken.py' in r)
ok('Docker problems', 'образ без фиксированной версии' in r and 'нет USER' in r and 'через оболочку' in r)
ok('CI problems', 'pull_request_target' in r and 'по ветке, а не по версии' in r)
ok('dependency hygiene', 'requirements.txt: 2 пакетов, без точной версии 1 (flask)' in r and 'нестрогие версии: left-pad' in r)
ok('project hygiene', 'нет .gitignore' in r and 'нет README' in r and 'lock-файла нет' in r)
ok('the most branching function is named', 'deep (app/main.py' in r)
ok('dependencies folders are skipped', 'node_modules' not in r)
ok('TODO counted', 'TODO/FIXME/HACK: 1' in r)
ok('the report fits a message', len(r) < 9000)

# the plate and the press
devtools.GRANTED['main.py'] = {'path': str(root / 'app' / 'main.py'), 't': time.time()}
plate = C.propose('x')
ok('a plate names the project, not the files', plate['project'] == 'shop' and plate['token'])
out = C.run(plate['token'])
ok('the press returns the report once', out['name'] == 'shop' and 'АУДИТ' in out['text'])
try:
    C.run(plate['token']); again = False
except PermissionError:
    again = True
ok('the press works once', again)
devtools.GRANTED.clear()
ok('no project known: said plainly', C.propose('x') == {'fail': 'noproject'})
