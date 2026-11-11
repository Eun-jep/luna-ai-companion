"""Her hands, part 6: build in a Unity project (scenes, objects, C# scripts from fixed templates).
Same rules as the Unreal and Godot bridges: the model never writes engine code. She names one operation from a short fixed list with
validated names and numbers; it runs only after the creator's press on a plate.
Unity has no headless scripting like Godot, so the project gets one small fixed editor script, Assets/Editor/LunaBridge.cs (this file
holds its text; it contains no network code and reads only JSON operations from the project's Temp folder or a command-line file).
If the editor is open on the project, the operation is dropped into Temp/luna/inbox and the editor script does it; if it is closed,
Unity runs once in batch mode on the project (the exact installed version is required). Scene files are copied to .luna_backup first.
Scripts are plain files and need neither the editor nor the helper.
Not checked against a real Unity install yet."""
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

TTL, MAX_PER_MINUTE = 120, 20
WAIT_OPEN, WAIT_BATCH = 90, 600     # seconds to wait for an open editor (it may recompile) / for a batch run
PENDING = {}
_recent = []
_lock = threading.Lock()

NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,31}$')
NUM = re.compile(r'^[+-]?\d{1,6}(?:\.\d{1,3})?$')
LIMIT = 100000.0
KINDS = ('empty', 'cube', 'sphere', 'capsule', 'cylinder', 'plane', 'quad', 'camera', 'light', 'sprite')
DIMS = ('2d', '3d')

_INPUT = '''#if ENABLE_INPUT_SYSTEM && !ENABLE_LEGACY_INPUT_MANAGER
using UnityEngine.InputSystem;
#endif
'''
_AXES = '''#if ENABLE_INPUT_SYSTEM && !ENABLE_LEGACY_INPUT_MANAGER
        var k = Keyboard.current;
        if (k == null) return;
        float x = (k.dKey.isPressed || k.rightArrowKey.isPressed ? 1f : 0f) - (k.aKey.isPressed || k.leftArrowKey.isPressed ? 1f : 0f);
        float y = (k.wKey.isPressed || k.upArrowKey.isPressed ? 1f : 0f) - (k.sKey.isPressed || k.downArrowKey.isPressed ? 1f : 0f);
#else
        float x = Input.GetAxisRaw("Horizontal");
        float y = Input.GetAxisRaw("Vertical");
#endif
'''
TEMPLATES = {
    'mover2d': 'using UnityEngine;\n' + _INPUT + '\npublic class %NAME% : MonoBehaviour\n{\n    public float speed = 5f;\n\n    void Update()\n    {\n'
               + _AXES + '        transform.position += new Vector3(x, y, 0f) * speed * Time.deltaTime;\n    }\n}\n',
    'mover3d': 'using UnityEngine;\n' + _INPUT + '\npublic class %NAME% : MonoBehaviour\n{\n    public float speed = 5f;\n\n    void Update()\n    {\n'
               + _AXES + '        transform.position += new Vector3(x, 0f, y) * speed * Time.deltaTime;\n    }\n}\n',
    'spinner': 'using UnityEngine;\n\npublic class %NAME% : MonoBehaviour\n{\n    public float degreesPerSecond = 90f;\n\n'
               '    void Update()\n    {\n        transform.Rotate(0f, degreesPerSecond * Time.deltaTime, 0f);\n    }\n}\n',
    'follow': 'using UnityEngine;\n\npublic class %NAME% : MonoBehaviour\n{\n    public Transform target;\n    public Vector3 offset = new Vector3(0f, 0f, -10f);\n'
              '    public float smoothing = 5f;\n\n    void LateUpdate()\n    {\n        if (target == null) return;\n'
              '        Vector3 wanted = target.position + offset;\n'
              '        transform.position = Vector3.Lerp(transform.position, wanted, 1f - Mathf.Exp(-smoothing * Time.deltaTime));\n    }\n}\n',
    'bobber': 'using UnityEngine;\n\npublic class %NAME% : MonoBehaviour\n{\n    public float height = 0.25f;\n    public float speed = 2f;\n    Vector3 start;\n\n'
              '    void Start()\n    {\n        start = transform.position;\n    }\n\n'
              '    void Update()\n    {\n        transform.position = start + Vector3.up * Mathf.Sin(Time.time * speed) * height;\n    }\n}\n',
    'health': 'using UnityEngine;\nusing UnityEngine.Events;\n\npublic class %NAME% : MonoBehaviour\n{\n    public int maxHealth = 100;\n    public int current;\n'
              '    public UnityEvent onDied;\n\n    void Start()\n    {\n        current = maxHealth;\n    }\n\n'
              '    public void Damage(int amount)\n    {\n        current = Mathf.Max(current - amount, 0);\n        if (current == 0) onDied.Invoke();\n    }\n\n'
              '    public void Heal(int amount)\n    {\n        current = Mathf.Min(current + amount, maxHealth);\n    }\n}\n',
    'empty': 'using UnityEngine;\n\npublic class %NAME% : MonoBehaviour\n{\n    void Start()\n    {\n    }\n}\n',
}

USAGE = ('scene <name> <2d|3d>; object <scene> <empty|cube|sphere|capsule|cylinder|plane|quad|camera|light|sprite> <name> [x y [z]]; '
         'move <scene> <object> x y [z]; script <name> <mover2d|mover3d|spinner|follow|bobber|health|empty>; attach <scene> <object> <script>; delete <scene> <object>; play')

HELPER_MARK = '// Luna bridge v1'
HELPER = HELPER_MARK + r'''
// Fixed code written by Luna's companion app. It only executes the operations below, read as JSON from
// <project>/Temp/luna/inbox (editor open) or from the file named by -lunaOp (batch mode). Names are checked again here.
#if UNITY_EDITOR
using System;
using System.IO;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

[InitializeOnLoad]
public static class LunaBridge
{
    [Serializable]
    class Op { public string op, scene, kind, dim, obj, script; public float[] at; }

    static readonly Regex Name = new Regex("^[A-Za-z][A-Za-z0-9_]{0,31}$");
    static readonly Regex Id = new Regex("^[0-9a-f]{16}$");
    static double next;

    static string Dir(string leaf) { return Path.Combine(Directory.GetCurrentDirectory(), "Temp", "luna", leaf); }

    static LunaBridge() { EditorApplication.update += Poll; }

    static void Poll()
    {
        if (EditorApplication.timeSinceStartup < next) return;
        next = EditorApplication.timeSinceStartup + 0.5;
        string inbox = Dir("inbox");
        if (!Directory.Exists(inbox)) return;
        foreach (string f in Directory.GetFiles(inbox, "*.json"))
        {
            string id = Path.GetFileNameWithoutExtension(f);
            string json = File.ReadAllText(f);
            File.Delete(f);
            if (!Id.IsMatch(id)) continue;
            Directory.CreateDirectory(Dir("outbox"));
            string tmp = Path.Combine(Dir("outbox"), id + ".tmp");
            File.WriteAllText(tmp, Execute(json));
            File.Move(tmp, Path.Combine(Dir("outbox"), id + ".json"));
        }
    }

    public static void RunBatch()
    {
        string[] a = Environment.GetCommandLineArgs();
        string op = null, output = null;
        for (int i = 0; i < a.Length - 1; i++)
        {
            if (a[i] == "-lunaOp") op = a[i + 1];
            if (a[i] == "-lunaOut") output = a[i + 1];
        }
        if (op == null || output == null) return;
        File.WriteAllText(output, Execute(File.ReadAllText(op)));
    }

    static string Ok(string what) { return "{\"done\":\"" + what + "\"}"; }
    static string Err(string code) { return "{\"error\":\"" + code + "\"}"; }

    static string Execute(string json)
    {
        try
        {
            Op o = JsonUtility.FromJson<Op>(json);
            if (o == null || string.IsNullOrEmpty(o.op)) return Err("failed");
            if (o.op == "play")
            {
                EditorApplication.isPlaying = true;
                return Ok("play");
            }
            if (EditorApplication.isPlayingOrWillChangePlaymode) return Err("busy");
            if (!Name.IsMatch(o.scene ?? "")) return Err("failed");
            string path = "Assets/Scenes/" + o.scene + ".unity";
            if (o.op == "scene") return NewScene(o, path);
            if (!File.Exists(path)) return Err("noscene");
            if (Busy()) return Err("busy");
            Scene scene = EditorSceneManager.OpenScene(path, OpenSceneMode.Single);
            switch (o.op)
            {
                case "object": return AddObject(o, scene);
                case "move": return Move(o, scene);
                case "attach": return Attach(o, scene);
                case "delete": return Delete(o, scene);
            }
            return Err("failed");
        }
        catch (Exception) { return Err("failed"); }
    }

    static bool Busy()
    {
        for (int i = 0; i < SceneManager.sceneCount; i++)
            if (SceneManager.GetSceneAt(i).isDirty) return true;
        return false;
    }

    static string NewScene(Op o, string path)
    {
        if (File.Exists(path)) return Err("exists");
        if (Busy()) return Err("busy");
        Directory.CreateDirectory("Assets/Scenes");
        bool three = o.dim == "3d";
        Scene s = EditorSceneManager.NewScene(three ? NewSceneSetup.DefaultGameObjects : NewSceneSetup.EmptyScene, NewSceneMode.Single);
        if (!three)
        {
            var cam = new GameObject("Main Camera");
            cam.tag = "MainCamera";
            var c = cam.AddComponent<Camera>();
            c.orthographic = true;
            cam.transform.position = new Vector3(0f, 0f, -10f);
        }
        return EditorSceneManager.SaveScene(s, path) ? Ok("scene") : Err("failed");
    }

    static GameObject Find(Scene scene, string name)
    {
        foreach (GameObject root in scene.GetRootGameObjects())
            foreach (Transform t in root.GetComponentsInChildren<Transform>(true))
                if (t.name == name) return t.gameObject;
        return null;
    }

    static Vector3 At(Op o)
    {
        return new Vector3(o.at[0], o.at[1], o.at.Length > 2 ? o.at[2] : 0f);
    }

    static string AddObject(Op o, Scene scene)
    {
        if (!Name.IsMatch(o.obj ?? "")) return Err("failed");
        if (Find(scene, o.obj) != null) return Err("exists");
        GameObject g;
        switch (o.kind)
        {
            case "empty": g = new GameObject(); break;
            case "cube": g = GameObject.CreatePrimitive(PrimitiveType.Cube); break;
            case "sphere": g = GameObject.CreatePrimitive(PrimitiveType.Sphere); break;
            case "capsule": g = GameObject.CreatePrimitive(PrimitiveType.Capsule); break;
            case "cylinder": g = GameObject.CreatePrimitive(PrimitiveType.Cylinder); break;
            case "plane": g = GameObject.CreatePrimitive(PrimitiveType.Plane); break;
            case "quad": g = GameObject.CreatePrimitive(PrimitiveType.Quad); break;
            case "camera": g = new GameObject(); g.AddComponent<Camera>(); break;
            case "light": g = new GameObject(); g.AddComponent<Light>(); break;
            case "sprite": g = new GameObject(); g.AddComponent<SpriteRenderer>(); break;
            default: return Err("failed");
        }
        g.name = o.obj;
        if (o.at != null && o.at.Length >= 2) g.transform.position = At(o);
        SceneManager.MoveGameObjectToScene(g, scene);
        return EditorSceneManager.SaveScene(scene) ? Ok("object") : Err("failed");
    }

    static string Move(Op o, Scene scene)
    {
        GameObject g = Find(scene, o.obj ?? "");
        if (g == null || o.at == null || o.at.Length < 2) return Err("nonode");
        g.transform.position = At(o);
        return EditorSceneManager.SaveScene(scene) ? Ok("move") : Err("failed");
    }

    static string Attach(Op o, Scene scene)
    {
        GameObject g = Find(scene, o.obj ?? "");
        if (g == null) return Err("nonode");
        if (!Name.IsMatch(o.script ?? "")) return Err("failed");
        string p = "Assets/Scripts/" + o.script + ".cs";
        if (!File.Exists(p)) return Err("noscript");
        var ms = AssetDatabase.LoadAssetAtPath<MonoScript>(p);
        Type t = ms != null ? ms.GetClass() : null;
        if (t == null) return Err("notcompiled");
        if (!typeof(MonoBehaviour).IsAssignableFrom(t)) return Err("mismatch");
        if (g.GetComponent(t) == null) g.AddComponent(t);
        return EditorSceneManager.SaveScene(scene) ? Ok("attach") : Err("failed");
    }

    static string Delete(Op o, Scene scene)
    {
        GameObject g = Find(scene, o.obj ?? "");
        if (g == null) return Err("nonode");
        UnityEngine.Object.DestroyImmediate(g);
        return EditorSceneManager.SaveScene(scene) ? Ok("delete") : Err("failed");
    }
}
#endif
'''


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
    """'object Main cube Box 0 1 2' -> a strictly validated operation dict; ValueError for anything else."""
    raw = ' '.join(str(text).replace(',', '.').split())
    if not raw or len(raw) > 160:
        raise ValueError('op')
    words = raw.split(' ')
    op, args = words[0].lower(), words[1:]
    if op == 'scene' and len(args) == 2 and args[1].lower() in DIMS:
        return {'op': 'scene', 'scene': _name(args[0]), 'dim': args[1].lower()}
    if op == 'object' and len(args) in (3, 5, 6) and args[1].lower() in KINDS:
        return {'op': 'object', 'scene': _name(args[0]), 'kind': args[1].lower(), 'obj': _name(args[2]), 'at': [_num(a) for a in args[3:]] or None}
    if op == 'move' and len(args) in (4, 5):
        return {'op': 'move', 'scene': _name(args[0]), 'obj': _name(args[1]), 'at': [_num(a) for a in args[2:]]}
    if op == 'script' and len(args) == 2 and args[1].lower() in TEMPLATES:
        return {'op': 'script', 'script': _name(args[0]), 'template': args[1].lower()}
    if op == 'attach' and len(args) == 3:
        return {'op': 'attach', 'scene': _name(args[0]), 'obj': _name(args[1]), 'script': _name(args[2])}
    if op == 'delete' and len(args) == 2:
        return {'op': 'delete', 'scene': _name(args[0]), 'obj': _name(args[1])}
    if op == 'play' and not args:
        return {'op': 'play'}
    raise ValueError('op')


def describe(o):
    """A short neutral line for the plate (fixed words, validated names and numbers)."""
    where = ' at %s' % ' '.join('%g' % v for v in o['at']) if o.get('at') else ''
    return {
        'scene': lambda: 'new %s scene %s' % (o['dim'].upper(), o['scene']),
        'object': lambda: 'add %s "%s" to %s%s' % (o.get('kind'), o.get('obj'), o.get('scene'), where),
        'move': lambda: 'move "%s" in %s%s' % (o.get('obj'), o.get('scene'), where),
        'script': lambda: 'new script %s.cs (%s template)' % (o.get('script'), o.get('template')),
        'attach': lambda: 'attach %s to "%s" in %s' % (o.get('script'), o.get('obj'), o.get('scene')),
        'delete': lambda: 'delete "%s" from %s' % (o.get('obj'), o.get('scene')),
        'play': lambda: 'press Play in the open editor',
    }[o['op']]()


# ---- which project and which engine ----

def _project_up(path):
    """The Unity project folder that contains this file, or ''."""
    cur = os.path.dirname(os.path.abspath(path))
    for _ in range(12):
        if os.path.isfile(os.path.join(cur, 'ProjectSettings', 'ProjectVersion.txt')) and os.path.isdir(os.path.join(cur, 'Assets')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return ''


def _info(root):
    text = devtools._read(os.path.join(root, 'ProjectSettings', 'ProjectVersion.txt'), 2000)
    ver = re.search(r'm_EditorVersion:\s*(\S+)', text)
    return {'root': root, 'name': os.path.basename(root), 'version': ver.group(1) if ver else ''}


def project():
    """The project she works in: the Unity project of the file shown to her last, else the only Unity project found. None when unclear."""
    for g in reversed(sorted(devtools.GRANTED.values(), key=lambda g: g['t'])):
        root = _project_up(g['path'])
        if root:
            return _info(root)
    found = [p for p in devtools.projects('unity') if _project_up(os.path.join(p['root'], 'Assets', 'x'))]
    return _info(found[0]['root']) if len(found) == 1 else None


def engine(version):
    """The installed Unity executable of exactly this version (a project opened in another version would be upgraded), or ''."""
    for e in devtools.engines('unity'):
        if e['version'] == version and os.path.isfile(e['exe']):
            return e['exe']
    return ''


def editor_open(root):
    """True when a Unity editor holds this project (its lock file exists and cannot be opened)."""
    lock = os.path.join(root, 'Temp', 'UnityLockfile')
    if not os.path.isfile(lock):
        return False
    try:
        with open(lock, 'r+b'):
            return False
    except OSError:
        return True


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
    if o['op'] == 'play' and not editor_open(proj['root']):
        return {'fail': 'neededitor'}
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
    src = os.path.join(root, 'Assets', 'Scenes', scene + '.unity')
    if os.path.isfile(src):
        folder = os.path.join(root, '.luna_backup')
        os.makedirs(folder, exist_ok=True)
        shutil.copy2(src, os.path.join(folder, '%s.%s.unity' % (scene, time.strftime('%Y%m%d-%H%M%S'))))


def install(root):
    """Put the fixed editor script into the project (once; refreshed only when it is our own older copy)."""
    path = os.path.join(root, 'Assets', 'Editor', 'LunaBridge.cs')
    if os.path.exists(path):
        old = devtools._read(path, 100000)
        if old == HELPER or not old.startswith('// Luna bridge'):
            return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(HELPER)
    return True


def _payload(o):
    keys = ('op', 'scene', 'kind', 'dim', 'obj', 'script', 'at')
    return {k: o[k] for k in keys if o.get(k) is not None}


def _via_editor(root, o, wait):
    """Drop the operation into the open editor's inbox and wait for its answer."""
    ident = secrets.token_hex(8)
    inbox, outbox = (os.path.join(root, 'Temp', 'luna', d) for d in ('inbox', 'outbox'))
    os.makedirs(inbox, exist_ok=True)
    os.makedirs(outbox, exist_ok=True)
    tmp = os.path.join(inbox, ident + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(_payload(o), f)
    os.replace(tmp, os.path.join(inbox, ident + '.json'))
    answer = os.path.join(outbox, ident + '.json')
    end = time.time() + wait
    while time.time() < end:
        if os.path.isfile(answer):
            try:
                with open(answer, encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError):
                time.sleep(0.2)
                continue
            os.remove(answer)
            return data
        time.sleep(0.3)
    try:
        os.remove(os.path.join(inbox, ident + '.json'))
    except OSError:
        pass
    raise RuntimeError('timeout')


def _via_batch(exe, root, o):
    """Unity once in batch mode on the closed project; returns the dict the editor script wrote."""
    folder = tempfile.mkdtemp(prefix='luna_un_')
    try:
        op, out = os.path.join(folder, 'op.json'), os.path.join(folder, 'out.json')
        with open(op, 'w', encoding='utf-8') as f:
            json.dump(_payload(o), f)
        try:
            subprocess.run([exe, '-batchmode', '-quit', '-nographics', '-projectPath', root, '-executeMethod', 'LunaBridge.RunBatch',
                            '-lunaOp', op, '-lunaOut', out, '-logFile', os.path.join(folder, 'unity.log')],
                           timeout=WAIT_BATCH, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('timeout') from exc
        except OSError as exc:
            raise RuntimeError('noengine') from exc
        try:
            with open(out, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError) as exc:
            raise RuntimeError('failed') from exc
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def run(o, runner=None, is_open=None, exe=None):
    """Do one validated operation. {'ok': True, ...} or {'ok': False, 'error': code}. `runner(o)`, `is_open`, `exe` are for tests."""
    now = time.time()
    _recent[:] = [t for t in _recent if now - t < 60]
    if len(_recent) >= MAX_PER_MINUTE:
        return {'ok': False, 'error': 'rate'}
    _recent.append(now)
    root = o.get('project') or ''
    if not root or not _project_up(os.path.join(root, 'Assets', 'x')):
        return {'ok': False, 'error': 'noproject'}
    if o['op'] == 'script':   # a plain file: no engine needed
        path = os.path.join(root, 'Assets', 'Scripts', o['script'] + '.cs')
        if os.path.exists(path):
            return {'ok': False, 'error': 'exists'}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(TEMPLATES[o['template']].replace('%NAME%', o['script']))
        return {'ok': True, 'op': 'script', 'name': o['script'] + '.cs'}
    opened = editor_open(root) if is_open is None else is_open
    if o['op'] == 'play' and not opened:
        return {'ok': False, 'error': 'neededitor'}
    if not opened:
        exe = exe if exe is not None else engine(_info(root)['version'])
        if not exe:
            return {'ok': False, 'error': 'noengine'}
    if o['op'] != 'scene' and o['op'] != 'play':
        _backup(root, o['scene'])
    try:
        install(root)
        with _lock:
            if runner:
                data = runner(o)
            elif opened:
                data = _via_editor(root, o, WAIT_OPEN)
            else:
                data = _via_batch(exe, root, o)
    except (RuntimeError, OSError) as exc:
        return {'ok': False, 'error': str(exc) if str(exc) in ('noengine', 'timeout') else 'failed'}
    if data.get('error'):
        return {'ok': False, 'error': data['error']}
    return {'ok': True, 'op': o['op'], 'name': o.get('obj') or o.get('scene') or ''}
