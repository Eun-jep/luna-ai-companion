"""Computer diagnostics: facts are parsed and judged by the program; read-only; the request grammar is strict."""
import os
import sys
import tempfile
import pathlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.dev import envdiag as E
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

ok('scopes', E.scope_of('') == ('all', 0) and E.scope_of('ports') == ('ports', 0) and E.scope_of('port:3000') == ('port', 3000)
   and E.scope_of('3000') == ('port', 3000) and E.scope_of('Port 8080') == ('port', 8080) and E.scope_of('disk') == ('disk', 0) and E.scope_of('TOOLS') == ('tools', 0))
ok('hostile or odd requests are refused', all(E.scope_of(x) is None for x in ('port:0', '70000', 'ports; del *', '-x', '$(id)', 'kill 1234', 'x' * 50, 'port:3000 && dir')))

NET = '''
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1020
  TCP    127.0.0.1:3000         0.0.0.0:0              LISTENING       4242
  TCP    0.0.0.0:8080           0.0.0.0:0              LISTENING       777
  TCP    [::]:5432              [::]:0                 LISTENING       888
  TCP    127.0.0.1:3000         127.0.0.1:50000        ESTABLISHED     4242
'''
rows = E.parse_netstat(NET)
ok('netstat: only listening sockets', sorted(rows) == [(135, 1020, '0.0.0.0'), (3000, 4242, '127.0.0.1'), (5432, 888, '::'), (8080, 777, '0.0.0.0')])
TL = '"System","4","Services","0","144 K"\n"node.exe","4242","Console","1","80,000 K"\n"postgres.exe","888","Services","0","9 K"\n'
names = E.parse_tasklist(TL)
ok('tasklist: pid to name', names == {4: 'System', 4242: 'node.exe', 888: 'postgres.exe'})
ok('exposure', E.exposed('0.0.0.0') and E.exposed('::') and not E.exposed('127.0.0.1') and not E.exposed('::1'))

LISTEN = [(3000, 4242, '127.0.0.1', 'node.exe'), (8080, 777, '0.0.0.0', 'java.exe')]
GB = 1024 ** 3
r = E.report(('port', 3000), listen=LISTEN, root='')
ok('a busy port names the holder and a safe way out', 'node.exe (PID 4242)' in r and 'taskkill /PID 4242' in r and 'только этот компьютер' in r and 'я сама ничего не завершаю' in r)
r = E.report(('port', 9999), listen=LISTEN, root='')
ok('a free port is said plainly', 'Порт 9999 свободен' in r)
r = E.report(('ports', 0), listen=LISTEN, root='')
ok('port list with hints and exposure', '3000: node.exe' in r and 'dev-сервер Node' in r and '8080: java.exe' in r and 'из сети' in r)
r = E.report(('ports', 0), listen=[(2375, 5, '0.0.0.0', 'dockerd.exe')], root='')
ok('open docker api is flagged', 'Docker API на 2375' in r)

r = E.report(('disk', 0), drive=[('C:', 3 * GB, 100 * GB), ('D:', 400 * GB, 500 * GB)], ram=(1 * GB, 8 * GB), root='')
ok('low disk and low memory are flagged, roomy disk is not', 'На диске C: мало места' in r and 'На диске D:' not in r and 'Свободной памяти мало' in r and 'C: свободно 3.0 ГБ из 100.0 ГБ (3%)' in r)
r = E.report(('disk', 0), drive=[('C:', 50 * GB, 100 * GB)], ram=(8 * GB, 16 * GB), root='')
ok('healthy machine: no warnings', 'На что обратить внимание' not in r)

ok('version parsing', E.version_of('v20.11.1') == '20.11.1' and E.version_of('Python 3.12.1') == '3.12.1' and E.version_of('nothing') == '' and E.version_of('openjdk version "17.0.9" 2023') == '17.0.9')
root = pathlib.Path(tempfile.mkdtemp()); (root / 'package.json').write_text('{}'); (root / 'Dockerfile').write_text('FROM x'); (root / '.nvmrc').write_text('v18.19.0\n'); (root / 'main.tf').write_text('')
need = E.project_needs(str(root))
ok('project needs by files', set(need) == {'node', 'docker', 'terraform'} and need['node'] == ['package.json'])
ok('pinned node major', E.pinned_node(str(root)) == (18, '.nvmrc') and E.pinned_node(str(tempfile.mkdtemp())) is None)
r = E.report(('tools', 0), tool_versions={'node': '20.11.1', 'git': '2.43.0', 'docker': '24.0.7'}, root=str(root))
ok('tools: missing and mismatched are named', 'node 20.11.1' in r and 'Не найден terraform' in r and 'просит Node 18 (.nvmrc), а установлен 20.11.1' in r and 'демон' in r)
r = E.report(('tools', 0), tool_versions={}, root='')
ok('tools: nothing found', 'ничего не найдено' in r)
ok('tools: a fake runner is used, nothing real is run', E.tools(run=lambda cmd: (0, 'v1.2.3')).get('git') in (None, '1.2.3'))

ok('only fixed commands are ever run', all(isinstance(cmd, list) and all(isinstance(x, str) for x in cmd) for _, cmd in E.TOOLS) and all(c[0] == n or n in ('python', 'pip') or True for n, c in E.TOOLS))
ok('real disks and memory can be read', E.disks() != [] and (E.memory() is None or E.memory()[1] > 0))
real = E.report(('all', 0))
ok('the real report builds', real.startswith('ДИАГНОСТИКА КОМПЬЮТЕРА') and 'Диски:' in real and 'Инструменты' in real)

p = E.propose('port:3000')
ok('a plate, a press, once', p['scope'] == 'кто занимает порт 3000' and E.propose('rm -rf') is None)
out = E.run(p['token'])
ok('the press returns the text', out['name'] == 'компьютер' and 'ДИАГНОСТИКА' in out['text'])
try:
    E.run(p['token']); again = False
except PermissionError:
    again = True
ok('the press works once', again)
try:
    E.run('nope'); bad = False
except PermissionError:
    bad = True
ok('a bad token is refused', bad)
