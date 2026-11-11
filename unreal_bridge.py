"""Her hands, part 4: work inside Unreal Engine through its own Python Remote Execution (stage 3).
The model never writes Python. It only names one operation from a short fixed list (spawn a shape or light, move / rotate /
scale / delete what is selected in the editor) with numbers; this module validates them and renders them into a template.
Every operation needs the creator's press on a plate first, and deleting asks like any risky step.
Unreal side: enable the 'Python Editor Script Plugin' and, in Project Settings > Plugins > Python, 'Enable Remote Execution'."""
import json
import os
import re
import secrets
import threading
import time
import types

import devtools

TTL, MAX_PER_MINUTE = 120, 20
PENDING = {}                     # token -> (operation, time): proposed by her, waiting for the creator's press
_recent = []
_module = {}
_lock = threading.Lock()

SHAPES = {'cube': 'Cube', 'sphere': 'Sphere', 'cylinder': 'Cylinder', 'cone': 'Cone', 'plane': 'Plane'}
LIGHTS = {'pointlight': 'PointLight', 'spotlight': 'SpotLight', 'directionallight': 'DirectionalLight'}
NUM = re.compile(r'^[+-]?\d{1,7}(?:\.\d{1,4})?$')
LIMIT_POS, LIMIT_ROT = 1000000.0, 360.0

# [ue:spawn cube], [ue:spawn sphere 0 0 100 2], [ue:move 0 0 50], [ue:rotate 0 90 0], [ue:scale 2], [ue:delete]
USAGE = ('spawn <cube|sphere|cylinder|cone|plane|pointlight|spotlight|directionallight> [x y z [scale]]; '
         'move dx dy dz; rotate pitch yaw roll; scale factor; delete')


def _num(s, limit):
    if not NUM.match(s):
        raise ValueError('number')
    v = float(s)
    if abs(v) > limit:
        raise ValueError('range')
    return v


def parse(text):
    """'spawn cube 0 0 100' -> a strictly validated operation dict; ValueError for anything else."""
    words = str(text).replace(',', '.').lower().split()
    if not words or len(words) > 6:
        raise ValueError('op')
    op, args = words[0], words[1:]
    if op == 'spawn':
        if not args or (args[0] not in SHAPES and args[0] not in LIGHTS) or len(args) not in (1, 4, 5):
            raise ValueError('spawn')
        out = {'op': 'spawn', 'what': args[0], 'at': None, 'scale': 1.0}
        if len(args) >= 4:
            out['at'] = [_num(a, LIMIT_POS) for a in args[1:4]]
        if len(args) == 5:
            s = _num(args[4], 100.0)
            if not 0.01 <= s <= 100:
                raise ValueError('scale')
            out['scale'] = s
        return out
    if op in ('move', 'rotate'):
        if len(args) != 3:
            raise ValueError(op)
        return {'op': op, 'v': [_num(a, LIMIT_POS if op == 'move' else LIMIT_ROT) for a in args]}
    if op == 'scale':
        if len(args) != 1:
            raise ValueError(op)
        f = _num(args[0], 100.0)
        if not 0.01 <= f <= 100:
            raise ValueError('scale')
        return {'op': 'scale', 'f': f}
    if op == 'delete' and not args:
        return {'op': 'delete'}
    raise ValueError('op')


def describe(o):
    """A short neutral line for the plate (numbers and fixed words only)."""
    if o['op'] == 'spawn':
        where = 'at %s' % ' '.join('%g' % v for v in o['at']) if o['at'] else 'in front of the editor camera'
        return 'spawn %s %s%s' % (o['what'], where, ' x%g' % o['scale'] if o['scale'] != 1 else '')
    if o['op'] == 'move':
        return 'move the selected by %s cm' % ' '.join('%g' % v for v in o['v'])
    if o['op'] == 'rotate':
        return 'rotate the selected by %s deg' % ' '.join('%g' % v for v in o['v'])
    if o['op'] == 'scale':
        return 'scale the selected x%g' % o['f']
    return 'delete the selected'


def propose(text):
    """She asked for an operation: validate it, remember it for two minutes, the creator decides. None if it is not valid."""
    try:
        o = parse(text)
    except ValueError:
        return None
    now = time.time()
    for k in [k for k, v in PENDING.items() if now - v[1] > TTL]:
        del PENDING[k]
    token = secrets.token_hex(8)
    PENDING[token] = (o, now)
    return {'token': token, 'text': describe(o), 'risky': o['op'] == 'delete'}


def take(token):
    entry = PENDING.pop(token, None) if isinstance(token, str) else None
    return entry[0] if entry and time.time() - entry[1] <= TTL else None


# ---- the Unreal side: a fixed template, filled with validated numbers only ----

HEAD = '''import unreal, math, json, contextlib
def _ok(**k):
    print("LUNA_RESULT:" + json.dumps(k))
try:
    _tx = unreal.ScopedEditorTransaction("Luna")
except Exception:
    _tx = contextlib.nullcontext()
'''
SPAWN = HEAD + '''
what, at, s = %(what)r, %(at)r, %(scale)r
shapes, lights = %(shapes)r, %(lights)r
if at is None:
    ok, loc, rot = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
    if ok:
        p, y = math.radians(rot.pitch), math.radians(rot.yaw)
        at = [loc.x + 500 * math.cos(p) * math.cos(y), loc.y + 500 * math.cos(p) * math.sin(y), loc.z + 500 * math.sin(p)]
    else:
        at = [0.0, 0.0, 100.0]
pos = unreal.Vector(at[0], at[1], at[2])
with _tx:
    if what in shapes:
        a = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, pos, unreal.Rotator(0, 0, 0))
        a.static_mesh_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        a.static_mesh_component.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/" + shapes[what] + "." + shapes[what]))
        a.set_actor_scale3d(unreal.Vector(s, s, s))
    else:
        a = unreal.EditorLevelLibrary.spawn_actor_from_class(getattr(unreal, lights[what]), pos, unreal.Rotator(0, 0, 0))
    a.set_actor_label("Luna_" + what)
unreal.EditorLevelLibrary.set_selected_level_actors([a])
_ok(done="spawn", name=a.get_actor_label())
'''
SELECTED = HEAD + '''
sel = unreal.EditorLevelLibrary.get_selected_level_actors()
if not sel:
    _ok(error="nothing_selected")
elif len(sel) > 20:
    _ok(error="too_many")
else:
%(body)s
    _ok(done=%(op)r, count=len(sel))
'''
BODY = {
    'move': '''    with _tx:
        for a in sel:
            l = a.get_actor_location()
            a.set_actor_location(unreal.Vector(l.x + %(a)r, l.y + %(b)r, l.z + %(c)r), False, False)''',
    'rotate': '''    with _tx:
        for a in sel:
            r = a.get_actor_rotation()
            a.set_actor_rotation(unreal.Rotator(r.roll + %(c)r, r.pitch + %(a)r, r.yaw + %(b)r), False)''',
    'scale': '''    with _tx:
        for a in sel:
            v = a.get_actor_scale3d()
            a.set_actor_scale3d(unreal.Vector(v.x * %(a)r, v.y * %(a)r, v.z * %(a)r))''',
    'delete': '''    with _tx:
        for a in sel:
            a.destroy_actor()''',
}


UNDO = '''import unreal, json
def _ok(**k):
    print("LUNA_RESULT:" + json.dumps(k))
unreal.SystemLibrary.execute_console_command(unreal.EditorLevelLibrary.get_editor_world(), "TRANSACTION UNDO")
_ok(done="undo", count=1)
'''


def undo(transport=None):
    """Take back the editor's latest step (only the journal calls this, never her: it is not in the list she can ask for)."""
    return run({'op': 'undo'}, transport)


def render(o):
    """The Python snippet for a validated operation."""
    if o['op'] == 'undo':
        return UNDO
    if o['op'] == 'spawn':
        return SPAWN % {'what': o['what'], 'at': o['at'], 'scale': float(o['scale']), 'shapes': SHAPES, 'lights': LIGHTS}
    v = o.get('v') or [o.get('f', 0.0), 0.0, 0.0]
    body = BODY[o['op']] % {'a': float(v[0]), 'b': float(v[1]), 'c': float(v[2])}
    return SELECTED % {'body': body, 'op': o['op']}


# ---- the connection ----

def _python_dirs():
    """Epic's remote_execution.py in every installed engine, newest first. Where the engines are is found by devtools."""
    rel = os.path.join('Engine', 'Plugins', 'Experimental', 'PythonScriptPlugin', 'Content', 'Python')
    seen, out = set(), []
    for root in devtools.unreal_roots():
        p = os.path.normpath(os.path.join(root, rel))
        if p.lower() not in seen and os.path.isfile(os.path.join(p, 'remote_execution.py')):
            seen.add(p.lower())
            out.append(p)
    return sorted(out, reverse=True)


def load_module():
    """Epic's own remote_execution.py from an installed engine (it is Epic's client for the protocol, we do not copy it)."""
    if 'm' not in _module:
        dirs = _python_dirs()
        if not dirs:
            raise RuntimeError('noengine')
        with open(os.path.join(dirs[0], 'remote_execution.py'), encoding='utf-8') as f:
            source = f.read()
        # Epic's UE 4.25 client passes json.loads(encoding=...), which Python 3.9+ removed: fixed in memory, the engine file stays as it is
        source = source.replace(", encoding='utf-8')", ')')
        mod = types.ModuleType('ue_remote_execution')
        exec(compile(source, 'remote_execution.py', 'exec'), mod.__dict__)   # noqa: S102 - Epic's own client file from the user's engine, loaded on purpose
        _module['m'] = mod
    return _module['m']


def _transport(code, wait=4.0):
    """Send one snippet to the editor and return its dict result. RuntimeError('noengine' | 'noeditor' | text)."""
    mod = load_module()
    ue = mod.RemoteExecution()
    ue.start()
    try:
        end = time.time() + wait
        while not ue.remote_nodes and time.time() < end:
            time.sleep(0.2)
        nodes = ue.remote_nodes
        if not nodes:
            raise RuntimeError('noeditor')
        try:
            ue.open_command_connection(nodes[0]['node_id'])
        except RuntimeError as exc:   # the editor was seen but never connected back (e.g. a busy or closing editor)
            raise RuntimeError('noeditor') from exc
        ue._command_connection._command_channel_socket.settimeout(20)   # an editor that hangs must not hang her
        return ue.run_command(code, unattended=True, exec_mode=mod.MODE_EXEC_FILE)
    except OSError as exc:
        raise RuntimeError('noeditor') from exc
    finally:
        try:
            ue.stop()
        except Exception:
            pass


def run(o, transport=None):
    """Do one validated operation. Returns {'ok': True, ...} or {'ok': False, 'error': code}."""
    now = time.time()
    _recent[:] = [t for t in _recent if now - t < 60]
    if len(_recent) >= MAX_PER_MINUTE:
        return {'ok': False, 'error': 'rate'}
    _recent.append(now)
    try:
        with _lock:   # the command port is fixed: one conversation with the editor at a time
            res = (transport or _transport)(render(o))
    except RuntimeError as exc:
        return {'ok': False, 'error': str(exc) if str(exc) in ('noengine', 'noeditor') else 'failed'}
    out = ''.join(str(x.get('output', '')) for x in res.get('output') or [] if isinstance(x, dict))
    m = re.search(r'LUNA_RESULT:(\{.*\})', out)
    data = json.loads(m.group(1)) if m else {}
    if not res.get('success') or not m:
        return {'ok': False, 'error': 'failed', 'detail': str(res.get('result'))[:200]}
    if data.get('error'):
        return {'ok': False, 'error': data['error']}
    return {'ok': True, 'op': o['op'], 'count': data.get('count', 1), 'name': data.get('name', '')}


_probe = {'t': 0.0, 'v': None}


def probe():
    """Is an Unreal editor answering right now? True / False, None when no engine is installed. Quick (about a second), cached 15 s."""
    if time.time() - _probe['t'] < 15:
        return _probe['v']
    try:
        mod = load_module()
    except (RuntimeError, OSError):
        return None
    with _lock:
        ue = mod.RemoteExecution()
        try:
            ue.start()
            end = time.time() + 1.3
            while not ue.remote_nodes and time.time() < end:
                time.sleep(0.1)
            seen = bool(ue.remote_nodes)
        except OSError:
            seen = False
        finally:
            try:
                ue.stop()
            except Exception:
                pass
    _probe.update(t=time.time(), v=seen)
    return seen
