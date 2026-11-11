"""Building in a Godot 4 project through godot_bridge.py: strict parsing, plates, the engine script template, plain-file scripts,
backups, project and engine choice. No real Godot: a fake runner stands in for the engine."""
import os
import sys, tempfile, pathlib, json, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import godot_bridge as G
import devtools
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

def bad(text):
    try:
        G.parse(text); return False
    except ValueError:
        return True

ok('scene', G.parse('scene Main 2d') == {'op': 'scene', 'scene': 'Main', 'kind': '2d'})
ok('node with a position', G.parse('node Main sprite2d Hero 100 50')['at'] == [100.0, 50.0] and G.parse('node Main Sprite2D Hero')['type'] == 'Sprite2D')
ok('3d node takes three numbers', G.parse('node World meshinstance3d Box 0 1 2')['at'] == [0.0, 1.0, 2.0] and bad('node World meshinstance3d Box 0 1'))
ok('a 2d node refuses three numbers', bad('node Main sprite2d Hero 1 2 3'))
ok('timer takes no position', bad('node Main timer T 1 2'))
ok('move, text, script, attach, delete, play', all(G.parse(x) for x in ('move Main Hero 5 6', 'text Main Title Привет мир', 'script Hero mover2d',
                                                                           'attach Main Hero Hero', 'delete Main Hero', 'play')))
ok('decimal comma is accepted', G.parse('move Main Hero 1,5 2')['at'] == [1.5, 2.0])
ok('unknown things are refused', all(bad(x) for x in ('', 'format c:', 'node Main Evil Hero', 'scene Main 4d', 'script Hero rm', 'play now')))
ok('names cannot carry code', all(bad(x) for x in ('scene "x" 2d', 'node Main sprite2d A"B', 'scene A;B 2d', 'node Main sprite2d ../x', 'scene 1abc 2d', 'scene ' + 'a' * 40 + ' 2d')))
ok('text cannot break out of its string', bad('text Main T say "hi"') and bad('text Main T back\\slash') and bad('text Main T ' + 'x' * 61))
ok('numbers are limited', bad('move Main Hero 99999999 0') and bad('move Main Hero 1e5 0') and bad('move Main Hero abc 0'))
ok('plate lines are plain', G.describe(G.parse('node Main sprite2d Hero 1 2')) == 'add Sprite2D "Hero" to Main at 1 2' and 'delete' in G.describe(G.parse('delete Main Hero')))

# the engine script
code = G.render(G.parse('node Main sprite2d Hero 100 50'), 'C:\\tmp\\r.json')
ok('script: the result path uses slashes and is a string constant', 'const RESULT := "C:/tmp/r.json"' in code)
ok('script: node, position, owner, save', 'Sprite2D.new()' in code and 'Vector2(100, 50)' in code and 'n.owner = root' in code and '_save(root, path)' in code)
ok('script: nothing returns a value from a void function', 'return _finish' not in G.render(G.parse('delete Main Hero'), 'r.json'))
ok('script: text goes in as a JSON string', 'n.text = "hello world"' in G.render(G.parse('text Main T hello world'), 'r.json'))
ok('script: even a hostile string stays inside its quotes', 'n.text = "a\\"b"' in G.render(dict(G.parse('text Main T hi'), text='a"b'), 'r.json'))
ok('script: label gets its own name as text', 'n.text = "Title"' in G.render(G.parse('node Main label Title'), 'r.json'))
ok('script: scene root type', 'Node3D.new()' in G.render(G.parse('scene World 3d'), 'r.json') and 'Control.new()' in G.render(G.parse('scene Menu ui'), 'r.json'))

# a project on disk
tmp = pathlib.Path(tempfile.mkdtemp())
proj = tmp / 'game'; (proj / 'scenes').mkdir(parents=True)
(proj / 'project.godot').write_text('config_version=5\n[application]\nconfig/name="Demo"\nconfig/features=PackedStringArray("4.2", "Forward Plus")\n', encoding='utf-8')
(proj / 'scenes' / 'Main.tscn').write_text('[gd_scene format=3]\n', encoding='utf-8')
(proj / 'scripts').mkdir()
(proj / 'scripts' / 'Hero.gd').write_text('extends CharacterBody2D\n', encoding='utf-8')
devtools.GRANTED['hero.gd'] = {'path': str(proj / 'scripts' / 'Hero.gd'), 't': 9e18}
info = G.project()
ok('the project is the one of the file she was shown', info and info['name'] == 'Demo' and info['major'] == 4)
plate = G.propose('node Main sprite2d Hero 1 2')
ok('a plate names the project and carries a token', plate and plate['project'] == 'Demo' and plate['token'] and not plate['risky'])
ok('delete is risky', G.propose('delete Main Hero')['risky'])
ok('an invalid request gives nothing', G.propose('format c:') is None)
op = G.take(plate['token'])
ok('the token works once', op and op['project'] == str(proj) and G.take(plate['token']) is None)

seen = []
def runner(code): seen.append(code); return {'done': 'node'}
r = G.run(op, runner=runner, exe='fake.exe')
ok('a node is added through the engine script', r == {'ok': True, 'op': 'node', 'name': 'Hero'} and 'Sprite2D.new()' in seen[0])
ok('the scene was copied before it changed', len(list((proj / '.luna_backup').glob('Main.*.tscn'))) == 1)
r = G.run(G.parse('scene Main 2d') | {'project': str(proj)}, runner=lambda c: {'error': 'exists'}, exe='fake.exe')
ok('engine errors come through', r == {'ok': False, 'error': 'exists'})
r = G.run(op, runner=runner, exe='')
ok('no engine installed: said plainly', r == {'ok': False, 'error': 'noengine'})

# scripts are plain files
s = G.parse('script Mover mover2d') | {'project': str(proj)}
r = G.run(s, exe='')
ok('a script needs no engine and is a Godot 4 template', r['ok'] and 'move_and_slide()' in (proj / 'scripts' / 'Mover.gd').read_text(encoding='utf-8'))
ok('a script is never overwritten', G.run(s, exe='') == {'ok': False, 'error': 'exists'})
ok('script files are plain LF text', b'\r' not in (proj / 'scripts' / 'Mover.gd').read_bytes())

# attach knows the script's base type
seen.clear()
G.run(G.parse('attach Main Hero Hero') | {'project': str(proj)}, runner=runner, exe='fake.exe')
ok('attach checks the base type from the script file', 'is_class("CharacterBody2D")' in seen[0])
r = G.run(G.parse('attach Main Hero Nope') | {'project': str(proj)}, runner=runner, exe='fake.exe')
ok('attach: a missing script is named', r == {'ok': False, 'error': 'noscript'})

# gates
ok('a project that is not there', G.run(G.parse('play') | {'project': str(tmp / 'nope')}, exe='x') == {'ok': False, 'error': 'noproject'})
(proj / 'project.godot').write_text('config/name="Old"\nconfig/features=PackedStringArray("3.5")\n', encoding='utf-8')
ok('Godot 3 is refused on the plate', G.propose('scene A 2d') == {'fail': 'version3'})
devtools.GRANTED.clear()
devtools._state.update(t=9e18, engines=[], projects=[])
ok('no project known: the plate fails', G.propose('scene A 2d') == {'fail': 'noproject'})
devtools._state.update(projects=[{'engine': 'godot', 'name': 'Demo', 'root': str(proj), 'file': str(proj / 'project.godot'), 'version': '4.2'}])
(proj / 'project.godot').write_text('config/name="Demo"\nconfig/features=PackedStringArray("4.2")\n', encoding='utf-8')
ok('the only Godot project is the default', G.project()['name'] == 'Demo')
exe3 = tmp / 'Godot_v3.5-stable_win64.exe'; exe4 = tmp / 'Godot_v4.2.1-stable_win64.exe'
exe3.write_text(''); exe4.write_text('')
devtools._state.update(engines=[{'engine': 'godot', 'version': '3.5', 'path': str(tmp), 'exe': str(exe3)},
                                {'engine': 'godot', 'version': '4.2.1', 'path': str(tmp), 'exe': str(exe4)}])
ok('the newest Godot 4 engine is used', G.engine() == str(exe4))
G._recent[:] = [9e18] * G.MAX_PER_MINUTE
ok('too many operations a minute are refused', G.run(op, runner=runner, exe='x') == {'ok': False, 'error': 'rate'})
