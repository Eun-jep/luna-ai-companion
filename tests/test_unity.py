"""Building in a Unity project through unity_bridge.py: strict parsing, plates, plain-file scripts, the fixed editor script,
the inbox hand-off to an open editor, backups, project choice. No real Unity: a fake editor answers the inbox."""
import os
import sys, tempfile, pathlib, json, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unity_bridge as U
import devtools
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

def bad(text):
    try:
        U.parse(text); return False
    except ValueError:
        return True

ok('scene', U.parse('scene Main 3d') == {'op': 'scene', 'scene': 'Main', 'dim': '3d'})
ok('object with and without a position', U.parse('object Main cube Box 0 1 2')['at'] == [0.0, 1.0, 2.0] and U.parse('object Main sphere Ball')['at'] is None
   and U.parse('object Main sprite S 1 2')['at'] == [1.0, 2.0])
ok('move, script, attach, delete, play', all(U.parse(x) for x in ('move Main Box 1 2', 'script Hero mover2d', 'attach Main Box Hero', 'delete Main Box', 'play')))
ok('decimal comma', U.parse('move Main Box 1,5 2 3')['at'] == [1.5, 2.0, 3.0])
ok('unknown things are refused', all(bad(x) for x in ('', 'format c:', 'object Main evil A', 'scene Main 4d', 'script Hero rm', 'play now', 'object Main cube A 1')))
ok('names cannot carry code', all(bad(x) for x in ('scene "x" 3d', 'object Main cube A"B', 'scene A;B 3d', 'object Main cube ../x', 'scene 1abc 3d', 'script A{} empty', 'scene ' + 'a' * 40 + ' 3d')))
ok('numbers are limited', bad('move Main Box 99999999 0') and bad('move Main Box 1e5 0') and bad('move Main Box abc 0'))
ok('plate lines are plain', U.describe(U.parse('object Main cube Box 1 2 3')) == 'add cube "Box" to Main at 1 2 3' and 'delete' in U.describe(U.parse('delete Main Box')))

# the editor script is fixed text: operations reach it only as JSON
ok('the helper has no network code and no process start', not any(w in U.HELPER for w in ('System.Net', 'UnityWebRequest', 'Process.Start', 'WebClient', 'Socket')))
ok('the helper checks names again and only reads from Temp/luna or -lunaOp', 'Name.IsMatch' in U.HELPER and '"Temp"' in U.HELPER and '-lunaOp' in U.HELPER)
ok('templates take the class name from the file name', all('class %NAME% : MonoBehaviour' in t for t in U.TEMPLATES.values()))
ok('movers work with both input systems', all('ENABLE_INPUT_SYSTEM' in U.TEMPLATES[k] and 'GetAxisRaw' in U.TEMPLATES[k] for k in ('mover2d', 'mover3d')))

# a project on disk
tmp = pathlib.Path(tempfile.mkdtemp())
proj = tmp / 'game'; (proj / 'Assets' / 'Scenes').mkdir(parents=True); (proj / 'ProjectSettings').mkdir()
(proj / 'ProjectSettings' / 'ProjectVersion.txt').write_text('m_EditorVersion: 2022.3.10f1\n', encoding='utf-8')
(proj / 'Assets' / 'Scenes' / 'Main.unity').write_text('%YAML 1.1\n', encoding='utf-8')
(proj / 'Assets' / 'Player.cs').write_text('using UnityEngine;\n', encoding='utf-8')
devtools.GRANTED['player.cs'] = {'path': str(proj / 'Assets' / 'Player.cs'), 't': 9e18}
info = U.project()
ok('the project is the one of the file she was shown', info and info['name'] == 'game' and info['version'] == '2022.3.10f1')
plate = U.propose('object Main cube Box 1 2 3')
ok('a plate names the project and carries a token', plate and plate['project'] == 'game' and plate['token'] and not plate['risky'])
ok('delete is risky', U.propose('delete Main Box')['risky'])
ok('an invalid request gives nothing', U.propose('format c:') is None)
ok('play needs an open editor, said at once', U.propose('play') == {'fail': 'neededitor'})
op = U.take(plate['token'])
ok('the token works once', op and op['project'] == str(proj) and U.take(plate['token']) is None)

# plain-file scripts
s = U.parse('script Mover mover2d') | {'project': str(proj)}
r = U.run(s, is_open=False, exe='')
text = (proj / 'Assets' / 'Scripts' / 'Mover.cs').read_text(encoding='utf-8')
ok('a script needs no editor and is named after its class', r == {'ok': True, 'op': 'script', 'name': 'Mover.cs'} and 'class Mover : MonoBehaviour' in text)
ok('a script is never overwritten', U.run(s, is_open=False, exe='') == {'ok': False, 'error': 'exists'})
ok('script files are plain LF text', b'\r' not in (proj / 'Assets' / 'Scripts' / 'Mover.cs').read_bytes())
ok('a script does not install the helper', not (proj / 'Assets' / 'Editor').exists())

# scene operations: closed editor needs the exact engine
ok('closed editor and no matching Unity: said plainly', U.run(op, is_open=False, exe='') == {'ok': False, 'error': 'noengine'})
got = []
r = U.run(op, runner=lambda o: got.append(o) or {'done': 'object'}, is_open=False, exe='fake.exe')
ok('the operation reaches the runner as plain data', r == {'ok': True, 'op': 'object', 'name': 'Box'} and got[0]['kind'] == 'cube')
ok('the helper was installed once', (proj / 'Assets' / 'Editor' / 'LunaBridge.cs').read_text(encoding='utf-8') == U.HELPER)
ok('the scene was copied before it changed', len(list((proj / '.luna_backup').glob('Main.*.unity'))) == 1)
(proj / 'Assets' / 'Editor' / 'LunaBridge.cs').write_text('// mine\nclass X {}\n', encoding='utf-8')
U.run(op, runner=lambda o: {'done': 'object'}, is_open=False, exe='x')
ok('a file that is not ours is never overwritten', (proj / 'Assets' / 'Editor' / 'LunaBridge.cs').read_text(encoding='utf-8').startswith('// mine'))
(proj / 'Assets' / 'Editor' / 'LunaBridge.cs').write_text(U.HELPER_MARK + '\nold\n', encoding='utf-8')
U.run(op, runner=lambda o: {'done': 'object'}, is_open=False, exe='x')
ok('our own older copy is refreshed', (proj / 'Assets' / 'Editor' / 'LunaBridge.cs').read_text(encoding='utf-8') == U.HELPER)
ok('engine errors come through', U.run(op, runner=lambda o: {'error': 'nonode'}, is_open=False, exe='x') == {'ok': False, 'error': 'nonode'})
ok('a runner that dies is a plain failure', U.run(op, runner=lambda o: (_ for _ in ()).throw(RuntimeError('boom')), is_open=False, exe='x') == {'ok': False, 'error': 'failed'})

# an open editor: the fake editor answers from the inbox
def editor():
    inbox, outbox = proj / 'Temp' / 'luna' / 'inbox', proj / 'Temp' / 'luna' / 'outbox'
    for _ in range(100):
        for f in list(inbox.glob('*.json')) if inbox.exists() else []:
            d = json.loads(f.read_text(encoding='utf-8')); f.unlink()
            (outbox / (f.stem + '.tmp')).write_text(json.dumps({'done': d['op']} if d['op'] != 'attach' else {'error': 'notcompiled'}))
            os.replace(outbox / (f.stem + '.tmp'), outbox / (f.stem + '.json'))
            seen.append(d)
        time.sleep(0.05)
seen = []
(proj / 'Assets' / 'Editor' / 'LunaBridge.cs').write_text(U.HELPER, encoding='utf-8')
threading.Thread(target=editor, daemon=True).start()
r = U.run(op, is_open=True)
ok('an open editor gets the operation through the inbox', r == {'ok': True, 'op': 'object', 'name': 'Box'} and seen[0]['obj'] == 'Box' and 'project' not in seen[0])
r = U.run(U.parse('attach Main Box Hero') | {'project': str(proj)}, is_open=True)
ok('the editor script can answer with its own error', r == {'ok': False, 'error': 'notcompiled'})
r = U.run(U.parse('play') | {'project': str(proj)}, is_open=True)
ok('play goes through the editor', r['ok'] and seen[-1]['op'] == 'play')
U.WAIT_OPEN = 0.3
dead = tmp / 'dead'; (dead / 'Assets').mkdir(parents=True); (dead / 'ProjectSettings').mkdir()
(dead / 'ProjectSettings' / 'ProjectVersion.txt').write_text('m_EditorVersion: 2022.3.10f1\n', encoding='utf-8')
ok('an editor that does not answer times out', U.run(U.parse('delete Main Box') | {'project': str(dead)}, is_open=True) == {'ok': False, 'error': 'timeout'})
ok('the unanswered request is withdrawn from the inbox', not list((dead / 'Temp' / 'luna' / 'inbox').glob('*.json')))

# gates
ok('a project that is not there', U.run(U.parse('play') | {'project': str(tmp / 'nope')}, is_open=True) == {'ok': False, 'error': 'noproject'})
devtools.GRANTED.clear()
devtools._state.update(t=9e18, engines=[], projects=[])
ok('no project known: the plate fails', U.propose('scene A 3d') == {'fail': 'noproject'})
devtools._state.update(projects=[{'engine': 'unity', 'name': 'game', 'root': str(proj), 'file': str(proj), 'version': '2022.3.10f1'}])
ok('the only Unity project is the default', U.project()['name'] == 'game')
exe = tmp / 'Unity.exe'; exe.write_text('')
devtools._state.update(engines=[{'engine': 'unity', 'version': '2021.3.1f1', 'path': str(tmp), 'exe': str(exe)},
                                {'engine': 'unity', 'version': '2022.3.10f1', 'path': str(tmp), 'exe': str(exe)}])
ok('the engine must be the project\'s own version', U.engine('2022.3.10f1') == str(exe) and U.engine('2020.1.1f1') == '')
U._recent[:] = [9e18] * U.MAX_PER_MINUTE
ok('too many operations a minute are refused', U.run(op, runner=lambda o: {}, is_open=True) == {'ok': False, 'error': 'rate'})
