"""Her hands, part 5: build in a Godot 4 project (scenes, nodes, scripts from fixed templates, a test run).
Like the Unreal bridge, the model never writes the engine script. She names one operation from a short fixed list with
validated names and numbers; this module renders it into a template, and it runs only after the creator's press on a plate.
The engine runs headless on the project folder (godot --headless --path <project> --script <tool>.gd), so the editor does not
have to be open; an open editor will offer to reload the changed scene. Every scene is copied to .luna_backup before it changes.
Not checked against a real Godot install yet: the template follows the Godot 4 API."""
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time

import devtools

TTL, MAX_PER_MINUTE, TIMEOUT = 120, 20, 60
PENDING = {}                     # token -> (operation, time): proposed by her, waiting for the creator's press
_recent = []
_lock = threading.Lock()

NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,31}$')
NUM = re.compile(r'^[+-]?\d{1,6}(?:\.\d{1,3})?$')
TEXT = re.compile(r'^[^"\\\x00-\x1f]{1,60}$')
LIMIT = 100000.0

ROOTS = {'2d': 'Node2D', '3d': 'Node3D', 'ui': 'Control'}
# node type -> (dimension for the position, lines run on the new node `n`)
TYPES = {
    'Node2D': ('2d', ''), 'Sprite2D': ('2d', 'if FileAccess.file_exists("res://icon.svg"):\n\t\tn.texture = load("res://icon.svg")'),
    'Camera2D': ('2d', ''), 'CharacterBody2D': ('2d', ''), 'StaticBody2D': ('2d', ''), 'RigidBody2D': ('2d', ''), 'Area2D': ('2d', ''),
    'CollisionShape2D': ('2d', 'var s := RectangleShape2D.new()\n\ts.size = Vector2(32, 32)\n\tn.shape = s'),
    'Label': ('ui', 'n.text = "%(name)s"'), 'Button': ('ui', 'n.text = "%(name)s"'), 'ColorRect': ('ui', ''), 'Panel': ('ui', ''),
    'TextureRect': ('ui', ''), 'VBoxContainer': ('ui', ''), 'HBoxContainer': ('ui', ''),
    'Node3D': ('3d', ''), 'Camera3D': ('3d', ''), 'DirectionalLight3D': ('3d', ''), 'OmniLight3D': ('3d', ''),
    'MeshInstance3D': ('3d', 'n.mesh = BoxMesh.new()'), 'CharacterBody3D': ('3d', ''), 'StaticBody3D': ('3d', ''),
    'CollisionShape3D': ('3d', 'n.shape = BoxShape3D.new()'),
    'Timer': ('none', ''), 'AudioStreamPlayer': ('none', ''), 'Node': ('none', ''),
}
LOWER = {k.lower(): k for k in TYPES}

TEMPLATES = {
    'mover2d': ('CharacterBody2D', 'extends CharacterBody2D\n\n@export var speed: float = 200.0\n\n'
                'func _physics_process(_delta: float) -> void:\n\tvar dir := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")\n'
                '\tvelocity = dir * speed\n\tmove_and_slide()\n'),
    'platformer2d': ('CharacterBody2D', 'extends CharacterBody2D\n\n@export var speed: float = 220.0\n@export var jump_velocity: float = -380.0\n'
                     'var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")\n\n'
                     'func _physics_process(delta: float) -> void:\n\tif not is_on_floor():\n\t\tvelocity.y += gravity * delta\n'
                     '\tif Input.is_action_just_pressed("ui_accept") and is_on_floor():\n\t\tvelocity.y = jump_velocity\n'
                     '\tvelocity.x = Input.get_axis("ui_left", "ui_right") * speed\n\tmove_and_slide()\n'),
    'spinner': ('Node2D', 'extends Node2D\n\n@export var degrees_per_second: float = 90.0\n\n'
                'func _process(delta: float) -> void:\n\trotation_degrees += degrees_per_second * delta\n'),
    'topdown2d': ('CharacterBody2D', 'extends CharacterBody2D\n\n@export var speed: float = 200.0\n@export var acceleration: float = 1200.0\n@export var friction: float = 1000.0\n\n'
                  'func _physics_process(delta: float) -> void:\n\tvar dir := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")\n'
                  '\tif dir != Vector2.ZERO:\n\t\tvelocity = velocity.move_toward(dir * speed, acceleration * delta)\n'
                  '\telse:\n\t\tvelocity = velocity.move_toward(Vector2.ZERO, friction * delta)\n\tmove_and_slide()\n'),
    'follow_camera2d': ('Camera2D', 'extends Camera2D\n\n## Who to follow: set it in the inspector, or name the node "Player" next to this camera.\n'
                        '@export var target_path: NodePath\n@export var smoothing: float = 6.0\n\n'
                        'func _process(delta: float) -> void:\n\tvar target := get_node_or_null(target_path) as Node2D\n'
                        '\tif target == null and get_parent() != null:\n\t\ttarget = get_parent().get_node_or_null("Player") as Node2D\n'
                        '\tif target:\n\t\tglobal_position = global_position.lerp(target.global_position, clamp(smoothing * delta, 0.0, 1.0))\n'),
    'bullet2d': ('Area2D', 'extends Area2D\n\n@export var speed: float = 400.0\n@export var lifetime: float = 2.0\n\n'
                 'func _ready() -> void:\n\tget_tree().create_timer(lifetime).timeout.connect(queue_free)\n\n'
                 'func _physics_process(delta: float) -> void:\n\tposition += Vector2.RIGHT.rotated(rotation) * speed * delta\n'),
    'health': ('Node', 'extends Node\n\nsignal health_changed(current: int, maximum: int)\nsignal died\n\n@export var max_health: int = 100\nvar current: int\n\n'
               'func _ready() -> void:\n\tcurrent = max_health\n\n'
               'func damage(amount: int) -> void:\n\tcurrent = max(current - amount, 0)\n\thealth_changed.emit(current, max_health)\n\tif current == 0:\n\t\tdied.emit()\n\n'
               'func heal(amount: int) -> void:\n\tcurrent = min(current + amount, max_health)\n\thealth_changed.emit(current, max_health)\n'),
    'mover3d': ('CharacterBody3D', 'extends CharacterBody3D\n\n@export var speed: float = 5.0\n@export var jump_velocity: float = 4.5\n'
                'var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")\n\n'
                'func _physics_process(delta: float) -> void:\n\tif not is_on_floor():\n\t\tvelocity.y -= gravity * delta\n'
                '\tif Input.is_action_just_pressed("ui_accept") and is_on_floor():\n\t\tvelocity.y = jump_velocity\n'
                '\tvar input_dir := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")\n'
                '\tvar dir := (transform.basis * Vector3(input_dir.x, 0.0, input_dir.y)).normalized()\n'
                '\tvelocity.x = dir.x * speed\n\tvelocity.z = dir.z * speed\n\tmove_and_slide()\n'),
    'spinner3d': ('Node3D', 'extends Node3D\n\n@export var degrees_per_second: float = 90.0\n\n'
                  'func _process(delta: float) -> void:\n\trotation_degrees.y += degrees_per_second * delta\n'),
    'empty': ('Node', 'extends Node\n\n\nfunc _ready() -> void:\n\tpass\n'),
}

USAGE = ('scene <name> <2d|3d|ui>; node <scene> <type> <name> [x y [z]]; move <scene> <node> x y [z]; text <scene> <node> <words>; '
         'script <name> <mover2d|platformer2d|topdown2d|follow_camera2d|bullet2d|health|mover3d|spinner|spinner3d|empty>; attach <scene> <node> <script>; delete <scene> <node>; play')


def _num(s):
    if not NUM.match(s):
        raise ValueError('number')
    v = float(s)
    if abs(v) > LIMIT:
        raise ValueError('range')
    return v


def _name(s):
    if not NAME.match(s or ''):
        raise ValueError('name')
    return s


def parse(text):
    """'node Main sprite2d Hero 100 50' -> a strictly validated operation dict; ValueError for anything else."""
    raw = ' '.join(str(text).replace(',', '.').split())
    if not raw or len(raw) > 160:
        raise ValueError('op')
    words = raw.split(' ')
    op, args = words[0].lower(), words[1:]
    if op == 'scene' and len(args) == 2 and args[1].lower() in ROOTS:
        return {'op': 'scene', 'scene': _name(args[0]), 'kind': args[1].lower()}
    if op == 'node' and len(args) in (3, 5, 6):
        typ = LOWER.get(args[1].lower())
        if not typ:
            raise ValueError('type')
        dim = TYPES[typ][0]
        at = [_num(a) for a in args[3:]]
        if at and len(at) != (3 if dim == '3d' else 2) or (at and dim == 'none'):
            raise ValueError('position')
        return {'op': 'node', 'scene': _name(args[0]), 'type': typ, 'node': _name(args[2]), 'at': at or None}
    if op == 'move' and len(args) in (4, 5):
        at = [_num(a) for a in args[2:]]
        return {'op': 'move', 'scene': _name(args[0]), 'node': _name(args[1]), 'at': at}
    if op == 'text' and len(args) >= 3:
        words_text = ' '.join(args[2:])
        if not TEXT.match(words_text):
            raise ValueError('text')
        return {'op': 'text', 'scene': _name(args[0]), 'node': _name(args[1]), 'text': words_text}
    if op == 'script' and len(args) == 2 and args[1].lower() in TEMPLATES:
        return {'op': 'script', 'script': _name(args[0]), 'template': args[1].lower()}
    if op == 'attach' and len(args) == 3:
        return {'op': 'attach', 'scene': _name(args[0]), 'node': _name(args[1]), 'script': _name(args[2])}
    if op == 'delete' and len(args) == 2:
        return {'op': 'delete', 'scene': _name(args[0]), 'node': _name(args[1])}
    if op == 'play' and not args:
        return {'op': 'play'}
    raise ValueError('op')


def describe(o):
    """A short neutral line for the plate (fixed words, validated names and numbers)."""
    where = ' at %s' % ' '.join('%g' % v for v in o['at']) if o.get('at') else ''
    return {
        'scene': lambda: 'new scene %s (%s)' % (o['scene'], ROOTS[o['kind']]),
        'node': lambda: 'add %s "%s" to %s%s' % (o.get('type'), o.get('node'), o.get('scene'), where),
        'move': lambda: 'move "%s" in %s%s' % (o.get('node'), o.get('scene'), where),
        'text': lambda: 'set the text of "%s" in %s: %s' % (o.get('node'), o.get('scene'), o.get('text')),
        'script': lambda: 'new script %s.gd (%s template)' % (o.get('script'), o.get('template')),
        'attach': lambda: 'attach %s.gd to "%s" in %s' % (o.get('script'), o.get('node'), o.get('scene')),
        'delete': lambda: 'delete "%s" from %s' % (o.get('node'), o.get('scene')),
        'play': lambda: 'run the game',
    }[o['op']]()


# ---- which project and which engine ----

def _project_up(path):
    """The Godot project folder that contains this file, or ''."""
    cur = os.path.dirname(os.path.abspath(path))
    for _ in range(12):
        if os.path.isfile(os.path.join(cur, 'project.godot')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return ''


def project():
    """The project she works in: the Godot project of the file shown to her last, else the only Godot project found. None when unclear."""
    latest = sorted(devtools.GRANTED.values(), key=lambda g: g['t'])
    for g in reversed(latest):
        root = _project_up(g['path'])
        if root:
            return _info(root)
    found = devtools.projects('godot')
    return _info(found[0]['root']) if len(found) == 1 else None


def _info(root):
    text = devtools._read(os.path.join(root, 'project.godot'), 20000)
    name = re.search(r'config/name="([^"]+)"', text)
    ver = re.search(r'config/features=.*?"(\d+)\.(\d+)"', text)
    return {'root': root, 'name': name.group(1) if name else os.path.basename(root), 'major': int(ver.group(1)) if ver else 4}


def engine():
    """The newest installed Godot 4 executable, or ''."""
    best = ''
    for e in sorted(devtools.engines('godot'), key=lambda e: [int(x) for x in re.findall(r'\d+', e['version'])] or [0], reverse=True):
        if e['version'].startswith('3.') or not os.path.isfile(e['exe']):
            continue
        best = e['exe']
        break
    return best


# ---- the engine side: a fixed template, filled with validated names and numbers only ----

HEAD = '''extends SceneTree

const RESULT := %(result)s

func _finish(d: Dictionary) -> void:
	var f := FileAccess.open(RESULT, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(d))
		f.close()
	quit()

func _save(root: Node, path: String) -> bool:
	var ps := PackedScene.new()
	if ps.pack(root) != OK:
		return false
	return ResourceSaver.save(ps, path) == OK

func _initialize() -> void:
	var path := "res://scenes/%(scene)s.tscn"
%(body)s
'''
BODY = {
    'scene': '''	if FileAccess.file_exists(path):
		return _finish({"error": "exists"})
	DirAccess.make_dir_recursive_absolute("res://scenes")
	var root := %(root)s.new()
	root.name = "%(scene)s"
	_finish({"done": "scene"} if _save(root, path) else {"error": "failed"})''',
    'node': '''	var ps = load(path)
	if ps == null:
		return _finish({"error": "noscene"})
	var root: Node = ps.instantiate()
	if root.has_node("%(node)s"):
		return _finish({"error": "exists"})
	var n := %(type)s.new()
	n.name = "%(node)s"
	%(setup)s
	root.add_child(n)
	n.owner = root
	%(place)s
	_finish({"done": "node"} if _save(root, path) else {"error": "failed"})''',
    'move': '''	var ps = load(path)
	if ps == null:
		return _finish({"error": "noscene"})
	var root: Node = ps.instantiate()
	var n = root if "%(node)s" == "%(scene)s" else root.get_node_or_null("%(node)s")
	if n == null or not "position" in n:
		return _finish({"error": "nonode"})
	%(place)s
	_finish({"done": "move"} if _save(root, path) else {"error": "failed"})''',
    'text': '''	var ps = load(path)
	if ps == null:
		return _finish({"error": "noscene"})
	var root: Node = ps.instantiate()
	var n = root if "%(node)s" == "%(scene)s" else root.get_node_or_null("%(node)s")
	if n == null or not "text" in n:
		return _finish({"error": "nonode"})
	n.text = %(text)s
	_finish({"done": "text"} if _save(root, path) else {"error": "failed"})''',
    'attach': '''	var ps = load(path)
	if ps == null:
		return _finish({"error": "noscene"})
	var spath := "res://scripts/%(script)s.gd"
	if not FileAccess.file_exists(spath):
		return _finish({"error": "noscript"})
	var root: Node = ps.instantiate()
	var n = root if "%(node)s" == "%(scene)s" else root.get_node_or_null("%(node)s")
	if n == null:
		return _finish({"error": "nonode"})
	if not n.is_class("%(ext)s"):
		return _finish({"error": "mismatch"})
	n.set_script(load(spath))
	_finish({"done": "attach"} if _save(root, path) else {"error": "failed"})''',
    'delete': '''	var ps = load(path)
	if ps == null:
		return _finish({"error": "noscene"})
	var root: Node = ps.instantiate()
	var n = root.get_node_or_null("%(node)s")
	if n == null or n == root:
		return _finish({"error": "nonode"})
	n.get_parent().remove_child(n)
	n.free()
	_finish({"done": "delete"} if _save(root, path) else {"error": "failed"})''',
}


def _place(o):
    at = o.get('at')
    if not at:
        return 'pass'
    kind = TYPES.get(o.get('type'), ('3d' if len(at) == 3 else '2d',))[0] if o['op'] == 'node' else ('3d' if len(at) == 3 else '2d')
    vec = 'Vector3(%g, %g, %g)' % tuple(at) if kind == '3d' else 'Vector2(%g, %g)' % tuple(at[:2])
    return 'n.position = ' + vec


def render(o, result_path):
    """The engine script for a validated operation (everything inserted is a validated name, a number or a JSON string)."""
    scene = o.get('scene', '')
    parts = {'scene': scene, 'node': o.get('node', ''), 'type': o.get('type', ''), 'script': o.get('script', ''),
             'root': ROOTS.get(o.get('kind'), 'Node'), 'place': _place(o), 'text': json.dumps(o.get('text', '')),
             'ext': o.get('ext') or 'Node'}
    if o['op'] == 'node':
        parts['setup'] = (TYPES[o['type']][1] % {'name': o['node']}) if TYPES[o['type']][1] else 'pass'
    body = BODY[o['op']] % parts
    body = re.sub(r'(?m)^(\t+)return (_finish\(.*\))$', r'\1\2\n\1return', body)   # a void function returns nothing
    return HEAD % {'result': json.dumps(result_path.replace('\\', '/')), 'scene': scene, 'body': body}


# ---- proposing and doing ----

def propose(text):
    """She asked for an operation: validate it, remember it for two minutes, the creator decides.
    A plate dict, {'fail': code} when it cannot be done at all, or None when the request is not valid."""
    try:
        o = parse(text)
    except ValueError:
        return None
    proj = project()
    if not proj:
        return {'fail': 'noproject'}
    if proj['major'] < 4:
        return {'fail': 'version3'}
    o['project'] = proj['root']
    now = time.time()
    for k in [k for k, v in PENDING.items() if now - v[1] > TTL]:
        del PENDING[k]
    token = secrets.token_hex(8)
    PENDING[token] = (o, now)
    return {'token': token, 'text': describe(o), 'project': proj['name'], 'risky': o['op'] == 'delete'}


def take(token):
    entry = PENDING.pop(token, None) if isinstance(token, str) else None
    return entry[0] if entry and time.time() - entry[1] <= TTL else None


def _backup(root, scene):
    src = os.path.join(root, 'scenes', scene + '.tscn')
    if os.path.isfile(src):
        folder = os.path.join(root, '.luna_backup')
        os.makedirs(folder, exist_ok=True)
        shutil.copy2(src, os.path.join(folder, '%s.%s.tscn' % (scene, time.strftime('%Y%m%d-%H%M%S'))))


def _engine_run(exe, root, o):
    """Run one operation headless on the project; returns the dict the engine script wrote. RuntimeError(code) otherwise."""
    folder = tempfile.mkdtemp(prefix='luna_gd_')
    try:
        result = os.path.join(folder, 'result.json')
        script = os.path.join(folder, 'tool.gd')
        with open(script, 'w', encoding='utf-8', newline='\n') as f:
            f.write(render(o, result))
        try:
            subprocess.run([exe, '--headless', '--path', root, '--script', script], timeout=TIMEOUT, capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('timeout') from exc
        except OSError as exc:
            raise RuntimeError('noengine') from exc
        try:
            with open(result, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError) as exc:
            raise RuntimeError('failed') from exc
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def run(o, runner=None, exe=None):
    """Do one validated operation. {'ok': True, ...} or {'ok': False, 'error': code}. `runner(code)` and `exe` are for tests."""
    now = time.time()
    _recent[:] = [t for t in _recent if now - t < 60]
    if len(_recent) >= MAX_PER_MINUTE:
        return {'ok': False, 'error': 'rate'}
    _recent.append(now)
    root = o.get('project') or ''
    if not root or not os.path.isfile(os.path.join(root, 'project.godot')):
        return {'ok': False, 'error': 'noproject'}
    if o['op'] == 'script':   # a plain file: no engine needed
        folder, path = os.path.join(root, 'scripts'), os.path.join(root, 'scripts', o['script'] + '.gd')
        if os.path.exists(path):
            return {'ok': False, 'error': 'exists'}
        os.makedirs(folder, exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(TEMPLATES[o['template']][1])
        return {'ok': True, 'op': 'script', 'name': o['script'] + '.gd'}
    exe = exe if exe is not None else engine()
    if not exe:
        return {'ok': False, 'error': 'noengine'}
    if o['op'] == 'play':
        try:
            subprocess.Popen([exe, '--path', root], cwd=root)
        except OSError:
            return {'ok': False, 'error': 'noengine'}
        return {'ok': True, 'op': 'play', 'name': ''}
    if o['op'] == 'attach':   # the script's own base type must fit the node
        try:
            with open(os.path.join(root, 'scripts', o['script'] + '.gd'), encoding='utf-8') as f:
                m = re.search(r'(?m)^extends\s+(\w+)', f.read(20000))
        except OSError:
            return {'ok': False, 'error': 'noscript'}
        o = dict(o, ext=m.group(1) if m else 'Node')
    if o['op'] != 'scene':
        _backup(root, o['scene'])
    try:
        with _lock:
            data = runner(render(o, 'result.json')) if runner else _engine_run(exe, root, o)
    except RuntimeError as exc:
        return {'ok': False, 'error': str(exc) if str(exc) in ('noengine', 'timeout') else 'failed'}
    if data.get('error'):
        return {'ok': False, 'error': data['error']}
    return {'ok': True, 'op': o['op'], 'name': o.get('node') or o.get('scene') or ''}

