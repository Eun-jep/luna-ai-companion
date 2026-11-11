"""Her developer skills (part 5): she finds game engines, projects and code on this computer by herself, so nothing depends
on where anything is installed. Nothing is typed in by hand and nothing is hard-coded: the paths come from a scan
(drives, Epic launcher manifest, registry, Unity Hub, Steam-less downloads) and are never sent to the model, only
names and versions are.
What she can do with it: say how to connect an engine (the guides below are facts for the prompt, spoken in the language
of the talk), open a found project in its own engine (after the creator confirms), and read a found code file (after the
creator confirms; its text then goes to the model like a pasted message)."""
import ctypes
import json
import os
import re
import secrets
import string
import subprocess
import threading
import time
from collections import deque

from luna.dev import infra

SCAN_SECONDS, SCAN_TTL, TTL = 8.0, 900, 120
ENGINE_NAMES = {'unreal': 'Unreal Engine', 'unity': 'Unity', 'godot': 'Godot', 'renpy': "Ren'Py"}
SKIP = {'windows', '$recycle.bin', 'system volume information', 'programdata', 'users', 'appdata', 'perflogs', 'recovery',
        'msocache', 'node_modules', '__pycache__', 'venv', '.venv', 'site-packages', 'cache', 'temp', 'tmp', 'steamapps'}
CODE_SKIP = SKIP | {'binaries', 'intermediate', 'saved', 'deriveddatacache', 'library', 'obj', 'bin', 'build', 'dist',
                    'content', 'packages', 'plugins'}   # build output and assets: no code of the creator's own
CODE_EXT = {'.py', '.js', '.mjs', '.ts', '.tsx', '.jsx', '.cs', '.cpp', '.cc', '.c', '.h', '.hpp', '.inl', '.java', '.kt',
            '.rs', '.go', '.gd', '.rpy', '.lua', '.html', '.css', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.ini',
            '.cfg', '.log', '.shader', '.hlsl', '.glsl', '.gdshader', '.uproject', '.uplugin', '.tscn', '.tres', '.godot', '.sql',
            '.sh', '.bat', '.ps1', '.xml', '.csproj', '.sln', '.asmdef', '.cmake', '.gradle', '.swift', '.php', '.rb', '.tf', '.conf'}
SECRET_RE = re.compile(r'(^\.env|secret|credential|password|passwd|token|apikey|api_key|private|id_rsa|\.pem$|\.key$|\.pfx$|'
                       r'\.p12$|cookie|keystore|\.kdbx$)', re.I)
MAX_READ_BYTES, MAX_SEND_CHARS = 400000, 12000

_state = {'t': 0.0, 'engines': [], 'projects': [], 'busy': False}
_code = {'t': 0.0, 'items': [], 'busy': False}
GRANTED = {}                     # lower file name -> {'path','t'}: files the creator agreed to show her (the only ones she may propose changes to)
GRANT_TTL = 3600
FOUND = {}                       # token -> a code file or project she may open (single use)
_lock = threading.Lock()


def _env(name):
    return os.environ.get(name) or ''


def drives():
    """Fixed local disks only (no network or removable ones)."""
    out = []
    for c in string.ascii_uppercase:
        root = c + ':\\'
        try:
            if os.path.isdir(root) and ctypes.windll.kernel32.GetDriveTypeW(root) == 3:
                out.append(root)
        except (OSError, AttributeError):
            if os.path.isdir(root):
                out.append(root)
    return out


def _user_roots():
    home = _env('USERPROFILE') or os.path.expanduser('~')
    names = ('Desktop', 'Documents', 'Downloads', 'source', 'repos', 'Projects', 'Games')
    roots = [os.path.join(home, n) for n in names]
    if _env('OneDrive'):
        roots += [os.path.join(_env('OneDrive'), n) for n in ('Desktop', 'Documents')]
    return [r for r in dict.fromkeys(roots) if os.path.isdir(r)]


def _read(path, limit=200000):
    try:
        with open(path, encoding='utf-8-sig', errors='ignore') as f:
            return f.read(limit)
    except OSError:
        return ''


def _json(path):
    try:
        return json.loads(_read(path))
    except ValueError:
        return {}


# ---- the scan: engines and projects ----

def _unreal_exe(root):
    for name in ('UnrealEditor.exe', 'UE4Editor.exe'):
        p = os.path.join(root, 'Engine', 'Binaries', 'Win64', name)
        if os.path.isfile(p):
            return p
    return ''


def _unity_versions(editor_dir):
    out = []
    try:
        for v in os.listdir(editor_dir):
            exe = os.path.join(editor_dir, v, 'Editor', 'Unity.exe')
            if os.path.isfile(exe):
                out.append({'engine': 'unity', 'version': v, 'path': os.path.join(editor_dir, v), 'exe': exe})
    except OSError:
        pass
    return out


def _project_of(path, names, files):
    """What kind of project lives in this folder, if any: dict or None. `names` = lower name -> is_dir."""
    for fn in files:
        low = fn.lower()
        if low.endswith('.uproject'):
            data = _json(os.path.join(path, fn))
            return {'engine': 'unreal', 'name': fn[:-9], 'root': path, 'file': os.path.join(path, fn),
                    'version': str(data.get('EngineAssociation') or '')}
        if low == 'project.godot':
            text = _read(os.path.join(path, fn), 20000)
            name = re.search(r'config/name="([^"]+)"', text)
            ver = re.search(r'config/features=.*?"(\d+\.\d+)"', text)
            return {'engine': 'godot', 'name': name.group(1) if name else os.path.basename(path), 'root': path,
                    'file': os.path.join(path, fn), 'version': ver.group(1) if ver else ''}
    if names.get('projectsettings') and names.get('assets'):
        ver = re.search(r'm_EditorVersion:\s*(\S+)', _read(os.path.join(path, 'ProjectSettings', 'ProjectVersion.txt'), 4000))
        if ver:
            return {'engine': 'unity', 'name': os.path.basename(path), 'root': path, 'file': path, 'version': ver.group(1)}
    if names.get('game') is True:
        game = os.path.join(path, 'game')
        if os.path.isfile(os.path.join(game, 'script.rpy')) or os.path.isfile(os.path.join(game, 'options.rpy')):
            return {'engine': 'renpy', 'name': os.path.basename(path), 'root': path, 'file': game, 'version': ''}
    return None


def _scan_dirs(roots, started, engines, projects):
    """Breadth-first over (path, depth, max depth): the whole disk to a shallow depth, your own folders deeper."""
    queue = deque((r, 0, d) for r, d in roots)
    seen = set()
    while queue and time.time() - started < SCAN_SECONDS:
        path, depth, limit = queue.popleft()
        key = os.path.normcase(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            entries = list(os.scandir(path))
        except OSError:
            continue
        names, files, subdirs = {}, [], []
        for e in entries:
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                continue
            names[e.name.lower()] = is_dir
            (subdirs if is_dir else files).append(e)
        file_names = [e.name for e in files]
        proj = _project_of(path, names, file_names)
        if proj:
            projects.append(proj)
            continue   # no digging into a project: it is huge and not ours to index here
        for e in files:
            low = e.name.lower()
            if low.startswith('godot') and low.endswith('.exe') and 'console' not in low:
                m = re.search(r'(\d+\.\d+(?:\.\d+)?)', low)
                engines.append({'engine': 'godot', 'version': m.group(1) if m else '', 'path': path, 'exe': e.path})
        for e in subdirs:
            low = e.name.lower()
            if low in SKIP or low.startswith('.'):
                continue
            m = re.match(r'ue_(\d+\.\d+)', low)
            if m and os.path.isdir(os.path.join(e.path, 'Engine')):
                engines.append({'engine': 'unreal', 'version': m.group(1), 'path': e.path, 'exe': _unreal_exe(e.path)})
                continue
            if low == 'hub' and os.path.isdir(os.path.join(e.path, 'Editor')):
                engines.extend(_unity_versions(os.path.join(e.path, 'Editor')))
                continue
            if low.startswith('renpy-') and os.path.isfile(os.path.join(e.path, 'renpy.exe')):
                engines.append({'engine': 'renpy', 'version': re.sub(r'-?sdk$', '', low[6:]), 'path': e.path,
                                'exe': os.path.join(e.path, 'renpy.exe')})
                continue
            if depth + 1 < limit:
                queue.append((e.path, depth + 1, limit))


def _known_engines():
    """Places that name an install directly, no scanning needed."""
    out = []
    manifest = os.path.join(_env('ProgramData') or r'C:\ProgramData', 'Epic', 'UnrealEngineLauncher', 'LauncherInstalled.dat')
    for item in _json(manifest).get('InstallationList') or []:
        if isinstance(item, dict) and str(item.get('AppName', '')).upper().startswith('UE_'):
            out.append(item.get('InstallLocation') or '')
    if _env('LUNA_UE_ROOT'):
        out.append(_env('LUNA_UE_ROOT'))
    try:
        import winreg
        for hive, sub, values in ((winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\EpicGames\Unreal Engine', False),
                                  (winreg.HKEY_CURRENT_USER, r'Software\Epic Games\Unreal Engine\Builds', True)):
            try:
                with winreg.OpenKey(hive, sub) as k:
                    for i in range(winreg.QueryInfoKey(k)[1 if values else 0]):
                        if values:
                            out.append(winreg.EnumValue(k, i)[1])
                        else:
                            with winreg.OpenKey(k, winreg.EnumKey(k, i)) as v:
                                out.append(winreg.QueryValueEx(v, 'InstalledDirectory')[0])
            except OSError:
                pass
    except ImportError:
        pass
    engines = []
    for root in out:
        if isinstance(root, str) and os.path.isdir(os.path.join(root, 'Engine')):
            m = re.search(r'(\d+\.\d+)', os.path.basename(os.path.normpath(root)))
            ver = m.group(1) if m else _json(os.path.join(root, 'Engine', 'Build', 'Build.version')).get('MajorVersion')
            if not m and isinstance(ver, int):
                ver = '%s.%s' % (ver, _json(os.path.join(root, 'Engine', 'Build', 'Build.version')).get('MinorVersion', 0))
            engines.append({'engine': 'unreal', 'version': str(ver or ''), 'path': root, 'exe': _unreal_exe(root)})
    second = _json(os.path.join(_env('APPDATA'), 'UnityHub', 'secondaryInstallPath.json')) if _env('APPDATA') else {}
    second = second if isinstance(second, str) else ''
    for p in [second, os.path.join(_env('ProgramFiles') or r'C:\Program Files', 'Unity', 'Hub', 'Editor')]:
        if p and os.path.isdir(p):
            engines.extend(_unity_versions(p))
    return engines


def scan(force=False):
    """Look for engines and projects (cached 15 minutes). Returns (engines, projects)."""
    with _lock:
        if _state['busy'] or (not force and time.time() - _state['t'] < SCAN_TTL):
            return _state['engines'], _state['projects']
        _state['busy'] = True
    try:
        started, engines, projects = time.time(), _known_engines(), []
        roots = [(r, 5) for r in _user_roots()]
        roots += [(d, 3) for d in drives()]
        pf = [_env('ProgramFiles'), _env('ProgramFiles(x86)')]
        roots += [(p, 4) for p in pf if p and os.path.isdir(p)]
        _scan_dirs(roots, started, engines, projects)
        seen, uniq = set(), []
        for e in engines:
            k = (e['engine'], os.path.normcase(os.path.normpath(e['path'])))
            if k not in seen:
                seen.add(k)
                uniq.append(e)
        seen, uprojects = set(), []
        for p in projects:
            k = os.path.normcase(os.path.normpath(p['root']))
            if k not in seen:
                seen.add(k)
                uprojects.append(p)
        _state.update(t=time.time(), engines=uniq, projects=uprojects)
    finally:
        _state['busy'] = False
    return _state['engines'], _state['projects']


def engines(kind=None):
    scan()
    return [e for e in _state['engines'] if kind in (None, e['engine'])]


def projects(kind=None):
    scan()
    return [p for p in _state['projects'] if kind in (None, p['engine'])]


def unreal_roots():
    return [e['path'] for e in engines('unreal')]


# ---- facts for the prompt (names and versions only, never paths) ----

def unreal_health():
    """Per project: is the Python plugin enabled in the .uproject, is remote execution enabled in DefaultEngine.ini."""
    out = []
    for p in projects('unreal'):
        plugins = _json(p['file']).get('Plugins') or []
        plugin = any(isinstance(x, dict) and x.get('Name') == 'PythonScriptPlugin' and x.get('Enabled') for x in plugins)
        ini = _read(os.path.join(p['root'], 'Config', 'DefaultEngine.ini'), 100000)
        remote = bool(re.search(r'bRemoteExecution\s*=\s*True', ini, re.I))
        out.append({'name': p['name'], 'version': p['version'], 'plugin': plugin, 'remote': remote})
    return out


def facts():
    """What was found on this computer, as lines for the system prompt."""
    eng, proj = engines(), projects()
    if not eng and not proj:
        return 'Сканирование компьютера ничего не нашло: ни движков, ни проектов (возможно, поиск ещё идёт или они в нестандартном месте).'
    lines = []
    for kind, label in ENGINE_NAMES.items():
        vers = sorted({e['version'] for e in eng if e['engine'] == kind and e['version']}, reverse=True)
        n = len([e for e in eng if e['engine'] == kind])
        lines.append('- %s: %s' % (label, ('установлен (%s)' % ', '.join(vers) if vers else 'установлен') if n else 'установленный движок не найден'))
    for kind, label in ENGINE_NAMES.items():
        names = ['%s%s' % (p['name'], ' ' + p['version'] if p['version'] else '') for p in proj if p['engine'] == kind][:6]
        if names:
            lines.append('- проекты %s: %s' % (label, '; '.join(names)))
    health = unreal_health()
    for h in health[:4]:
        lines.append('- Unreal-проект %s: плагин Python %s в .uproject, Remote Execution %s в DefaultEngine.ini (подсказка: настройка могла быть включена и '
                     'в самом редакторе, файл это не покажет)' % (h['name'], 'включён' if h['plugin'] else 'НЕ включён',
                                                                  'включён' if h['remote'] else 'НЕ включён'))
    return '\n'.join(lines)


TOPIC_RES = {
    'unreal': re.compile(r'unreal|анр[еи]а?л|унр[еи]а?л|언리얼|アンリアル|\bue[45]\b|\bue ?(4|5)\b', re.I),
    'unity': re.compile(r'unity|юнити|유니티|ユニティ', re.I),
    'godot': re.compile(r'godot|годот|고도|ゴドー|ゴドット|gdscript', re.I),
    'renpy': re.compile(r"ren'?py|рен'?пи|ренпай|렌파이|レンパイ|レンピー", re.I),
    # what a colleague does in an IT team besides writing code
    'review': re.compile(r'code review|ревью|ревьюй|pull request|\bpr\b|мердж|merge|коммит|commit|\bdiff\b|рефактор|리뷰|풀 ?리퀘|커밋|レビュー|コミット', re.I),
    'debug': re.compile(r'отлад|дебаг|debug|traceback|stack ?trace|стек ?трейс|падает|вылетает|крэш|crash|не запускается|логи?\b|'
                        r'exception|디버그|충돌|로그|デバッグ|クラッシュ|ログ', re.I),
    'docs': re.compile(r'readme|документаци|тикет|баг-?репорт|bug report|постмортем|postmortem|стендап|standup|протокол встречи|итоги встречи|'
                       r'changelog|техзадани|спецификаци|\bтз\b|문서화|회의록|티켓|ドキュメント|議事録|チケット', re.I),
    'ops': re.compile(r'\bsql\b|regex|регуляр|\bgit\b|docker|ci/cd|пайплайн|pipeline|\bapi\b|\bjson\b|\byaml\b|\bbash\b|деплой|deploy|'
                      r'깃|도커|배포|デプロイ|ドッカー', re.I),
}
CODE_RE = re.compile(r'```|\bcode\b|\bbug\b|\bscript\b|\bfunction\b|\bcompile|\berror\b|traceback|exception|код\b|кода|коде|скрипт|баг|функци|ошибк|'
                     r'программ|разработ|코드|버그|스크립트|함수|오류|コード|バグ|スクリプト|関数|エラー|プログラ', re.I)


def topics(text):
    """Which engines (and whether code in general) the talk is about."""
    found = [k for k, rx in TOPIC_RES.items() if rx.search(text)]
    if found or CODE_RE.search(text):
        found.append('code')
    return found


GUIDES = {
    'unreal': (
        "Unreal Engine: ты умеешь строить в открытом редакторе (создать фигуру или свет, сдвинуть, повернуть, масштабировать, удалить "
        "выделенное) командой [ue:...], если включён переключатель «Луна может строить в Unreal Engine». Как подключить, по шагам: "
        "1) в редакторе Edit > Plugins найти «Python Editor Script Plugin» (раздел Scripting; в UE 4.25 он Experimental), включить, "
        "перезапустить редактор; 2) Edit > Project Settings > Plugins > Python, включить «Enable Remote Execution», снова перезапустить; "
        "3) в приложении включить «Луна может строить в Unreal Engine»; 4) открыть уровень и попросить, например «сделай куб». "
        "Где стоит движок, она находит сама, вводить пути не нужно, проект можно передать другому человеку. "
        "Если не отвечает: редактор должен быть открыт (не только лаунчер), оба пункта включены и редактор перезапущен после этого, "
        "VPN или брандмауэр могут мешать локальному мультикасту (UDP 239.0.0.1:6766), проект должен быть открыт в редакторе."),
    'unity': (
        "Unity: движок и проекты ты находишь сама и можешь открыть проект (после «да» создателя, через [find:название проекта]). "
        "В рабочем режиме ты строишь в проекте Unity командой [unity:...] (сцены, объекты, скрипты из шаблонов; создатель нажимает «Сделать»; "
        "в проект кладётся маленький файл Assets/Editor/LunaBridge.cs). Остальное: знания и код: C# скрипты (MonoBehaviour, ScriptableObject), "
        "сцены, префабы, физика, UI, оптимизация, разбор ошибок консоли; файл проекта можешь попросить показать через [read:имя файла]. "
        "Как работаешь: сначала узнай версию Unity и конвейер рендера (Built-in, URP, HDRP) и старая или новая система ввода (Input Manager или Input System), "
        "потому что от этого зависит код. Скрипты лежат в Assets/, имя файла = имя класса, поля с [SerializeField] видны в Инспекторе; "
        "связи (ссылки на объекты, префабы) создатель расставляет в редакторе, и об этом нужно сказать прямо: код сам их не создаст. "
        "Частые ловушки: Update против FixedUpdate для физики, Time.deltaTime, NullReference из-за непривязанной ссылки в Инспекторе, "
        "поиск в Update (Find, GetComponent каждый кадр), корутины и их остановка, порядок Awake/Start/OnEnable. "
        "Файлы .meta Unity создаёт сам: в новых проектах их не пиши. Разбирая ошибку консоли, читай первую строку и путь Assets/...:строка, а не весь стек."),
    'godot': (
        "Godot: движок и проекты (project.godot) ты находишь сама и можешь открыть проект (после «да» создателя, через [find:название]). "
        "В рабочем режиме ты строишь в проекте Godot 4 командой [gd:...] (сцены, узлы, скрипты из шаблонов, запуск игры; создатель нажимает «Сделать»), Godot 3 не поддерживается. Остальное: знания и код: GDScript, "
        "C#, узлы и сцены, сигналы, физика, UI, шейдеры, экспорт; файл проекта можешь попросить через [read:имя файла]. "
        "Как работаешь: сначала узнай версию (Godot 3 и Godot 4 сильно различаются): в 4 это @export, @onready, signal.connect(), "
        "CharacterBody2D/3D, move_and_slide() без аргументов, await вместо yield, super() вместо .method(); в 3 это export, onready, connect(\"сигнал\", self, \"метод\"), "
        "KinematicBody, yield. Сцены .tscn и ресурсы .tres текстовые, но их безопаснее собирать в редакторе, а не править руками: узлы, пути NodePath и "
        "идентификаторы легко сломать; код .gd и .shader правь смело. Частые ловушки: _process против _physics_process, get_node по неверному пути, "
        "сигнал не подключён, @onready до готовности дерева, группы и слои коллизий, автозагрузки (Autoload) для глобального состояния. "
        "Новую сцену можно описать словами и дать скрипт, а узлы пусть он добавит в редакторе: так надёжнее."),
    'renpy': (
        "Ren'Py: SDK и проекты (папка game с script.rpy) ты находишь сама и можешь запустить проект (после «да» создателя, через [find:название]). "
        "Файл, который он тебе показал, ты можешь предложить изменить блоком lunaedit, иначе пишешь код в блоках, создатель вставляет его сам. Помогаешь с "
        ".rpy: label, jump, menu, define, персонажи, переменные, screen language, ATL, сохранения, разбор ошибок; "
        "файл сценария можешь попросить показать через [read:script.rpy]. "
        "Как работаешь: Ren'Py очень чувствителен к отступам (4 пробела, без табуляции) и двоеточиям. Основы: define e = Character(\"Имя\", color=\"#c8ffc8\"), "
        "image bg room = \"room.png\", label start: ... return, scene bg room, show eileen happy, with dissolve, e \"реплика\", menu: с вариантами и отступами, "
        "jump и call, default и $ для переменных и флагов, if/elif/else, renpy.pause, play music. Отличай define (константа) от default (сохраняемая "
        "переменная). Частые ошибки: пропущен return или label, неверный отступ, ссылка на несуществующее изображение, кавычки в тексте реплики (экранируй \\\" или используй другие), "
        "переменная изменена через define. Ошибки смотри в traceback.txt или errors.txt рядом с проектом; ветвление держи читаемым: названия label по смыслу, "
        "флаги вида met_anna, общие развилки вынеси в отдельные label. Для новых сцен лучше сразу дай рабочий кусок script.rpy, который он может вставить."),
    'review': (
        "Ревью и коммиты: ты внимательный коллега-ревьюер. Смотри в таком порядке: 1) делает ли код то, что заявлено (логика, граничные случаи, пустые "
        "значения, ошибки и исключения); 2) безопасность (ввод пользователя, SQL и команды без экранирования, секреты в коде, права); "
        "3) надёжность и производительность (гонки, утечки, запросы в цикле); 4) читаемость и тесты. Говори по делу и по важности: сначала то, что ломает, "
        "потом то, что стоит поправить, мелкие придирки одной строкой или вовсе промолчи. К каждому замечанию: что не так, почему, как исправить. "
        "Хвали то, что удачно, коротко и честно, без лести. Если дифф не показан, попроси его, не выдумывай. "
        "Сообщение коммита: первая строка до ~70 символов в повелительном наклонении («Исправить…», «Добавить…»), пустая строка, затем зачем (не что). "
        "Описание PR: что изменено, зачем, как проверить, на что обратить внимание. Рефакторинг предлагай маленькими шагами, поведение при этом не меняй."),
    'debug': (
        "Отладка вместе: ты как напарник, которому рассказывают про баг («утка»). Метод: 1) что ожидалось и что происходит на самом деле; "
        "2) воспроизводится ли всегда, что менялось перед тем как сломалось; 3) читай ошибку с первой строки и места в его коде, а не весь стек; "
        "4) выдвини одну-две вероятные причины и как каждую проверить самым дешёвым способом (лог, печать значения, минимальный пример, откат изменения); "
        "5) только потом правка. Не угадывай вслепую набор правок: одна гипотеза, одна проверка. Если не хватает данных, попроси точное: текст ошибки, "
        "версию, кусок кода, команду запуска. Когда он вымотан и злится, сначала по-человечески поддержи («бывает, давай по шагам»), потом разбирайся. "
        "Если сама не уверена в причине, так и скажи и предложи, как это выяснить."),
    'docs': (
        "Документы и рабочая переписка: ты помогаешь писать ясно и коротко. README: что это, как поставить и запустить (команды в блоке), пример использования, "
        "где что лежит. Баг-репорт: заголовок по сути, шаги воспроизведения, ожидаемое и фактическое, окружение (версия, ОС), логи или скриншот. "
        "Тикет и задача: цель, критерии готовности, что вне рамок. Итоги встречи: решения, кто что делает и к какому сроку, открытые вопросы. "
        "Постмортем: что случилось, влияние, причина, что сделали, что изменим (без поиска виноватых). Стендап: вчера, сегодня, блокеры. "
        "Пиши так, как говорят в его команде, без канцелярита. Если нужен настоящий файл Word, Excel или PowerPoint, предложи его блоком lunadoc."),
    'ops': (
        "Инструменты разработчика: git (ветки, rebase против merge, отмена коммита, конфликты: объясняй, что команда сделает, и предупреждай о необратимом вроде "
        "reset --hard и push --force), SQL (проверяй условия соединения, индексы, N+1, всегда предупреждай про UPDATE и DELETE без WHERE), регулярные выражения "
        "(дай выражение, разбор по частям и пример совпадений), Docker и CI (образы, тома, порты, кэш, секреты не в образе), JSON и YAML (отступы, кавычки), "
        "bash и PowerShell (отличай синтаксис), REST API (метод, статус, заголовки, авторизация). Команды давай в блоке кода, по одной на шаг; опасные помечай словами. "
        "Секреты, пароли и токены не проси и не повторяй: если они попали в разговор, посоветуй их заменить."),
    'code': (
        "Код: ты разработчик и умеешь работать с любым языком и стеком: писать, объяснять, искать баги, ревьюить, рефакторить, "
        "оптимизировать, писать тесты. Правила: сначала коротко вслух (1–3 предложения) суть и что делать, а сам код клади в блок "
        "```язык ... ``` — он показывается в чате и НЕ озвучивается; никогда не зачитывай код вслух. Для пошаговой инструкции (подключение, "
        "установка) клади шаги в блок ```guide ... ``` обычным текстом, коротко, 3–8 пунктов; вслух только суть. Если нужно увидеть его "
        "код, а он не прислан, попроси прислать или найди файл командой [read:имя файла] (приложение само найдёт и спросит его «показать?»; "
        "ставь только имя и расширение, например [read:PlayerController.cs]). Не выдумывай содержимое файлов, API и вывод программ: не "
        "уверена — скажи. Код не запускаешь. Файл, который он тебе показал, ты можешь предложить изменить блоком lunaedit (формат дан отдельно), остальное он вставляет сам, так и говори. Комментарии в коде пиши на языке разговора. "
        "Как думаешь над кодом: сначала пойми цель и среду (язык, версия, фреймворк, что уже пробовал); если от этого зависит ответ и это неясно, спроси одно главное. "
        "Ищи корень проблемы, а не симптом: читай ошибку с первой строки, назови вероятную причину и как её проверить, и только потом правку. "
        "Меняй как можно меньше и объясняй, почему; не переписывай то, о чём не просили. Предупреждай о побочных эффектах и о том, что ты не проверила запуском. "
        "Если вариантов несколько, назови лучший и коротко почему, остальные одной строкой. Если не знаешь API или версию, скажи об этом, а не выдумывай. "
        "Говори с ним как коллега и близкий человек, а не как справочник: без лекций и без сухих списков, если он просто застрял и ему нужна поддержка."),
}


def dev_block(text, history):
    """The developer section of the system prompt for this turn, or ''. Looks at the message and the last few lines."""
    found = topics(' '.join([text] + history))
    if not found:
        return ''
    parts = ['\n\nТы ещё и разработчица. Факты о его компьютере (найдены сканированием, он ничего не вводил; пути тебе не нужны):\n' + facts()]
    parts += [GUIDES[k] for k in found if k in GUIDES and k != 'code']
    parts.append(GUIDES['code'])
    return '\n\n'.join(parts)


# ---- opening a found project in its own engine ----

def project_items():
    """Findable entries for agent.py: every project found, labelled with its engine."""
    items = []
    for p in projects():
        label = '%s (%s%s)' % (p['name'], ENGINE_NAMES[p['engine']], ' ' + p['version'] if p['version'] else '')
        items.append({'label': label, 'kind': 'proj', 'target': p, 'where': p['root'], 'rank': 0})
    return items


def _engine_for(p):
    cands = engines(p['engine'])
    exact = [e for e in cands if p['version'] and e['version'] and (e['version'].startswith(p['version']) or p['version'].startswith(e['version']))]
    pool = exact or sorted(cands, key=lambda e: e['version'], reverse=True)
    return pool[0] if pool else None


def launch_project(p):
    """Open a project that this module itself found: through its engine, no shell, arguments fixed here."""
    known = [x for x in projects() if os.path.normcase(x['root']) == os.path.normcase(str(p.get('root')))]
    if not known or not os.path.exists(known[0]['file']):
        raise OSError('gone')
    p = known[0]
    if p['engine'] == 'unreal':
        os.startfile(p['file'])   # the .uproject association picks the right editor version
        return
    eng = _engine_for(p)
    if not eng or not eng['exe']:
        raise OSError('noengine')
    args = {'unity': ['-projectPath', p['root']], 'godot': ['--path', p['root'], '-e'], 'renpy': [p['root']]}[p['engine']]
    subprocess.Popen([eng['exe']] + args, cwd=os.path.dirname(eng['exe']) or None)


# ---- reading a found code file ----

def _code_index():
    if time.time() - _code['t'] < SCAN_TTL:
        return _code['items']
    items, started = [], time.time()
    roots = [(p['root'], 7) for p in projects()] + [(r, 4) for r in _user_roots()]
    queue, seen = deque((r, 0, d) for r, d in roots), set()
    while queue and len(items) < 60000 and time.time() - started < SCAN_SECONDS:
        path, depth, limit = queue.popleft()
        key = os.path.normcase(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            entries = list(os.scandir(path))
        except OSError:
            continue
        for e in entries:
            low = e.name.lower()
            try:
                if e.is_dir(follow_symlinks=False):
                    if low not in CODE_SKIP and not low.startswith('.') and depth + 1 < limit:
                        queue.append((e.path, depth + 1, limit))
                elif os.path.splitext(low)[1] in CODE_EXT and not SECRET_RE.search(low):
                    items.append({'label': e.name, 'path': e.path})
            except OSError:
                continue
    _code.update(t=time.time(), items=items)
    return items


def find_code(query, limit=3):
    """Code files whose name matches what she asked for, best first, each with a one-time token."""
    words = re.findall(r'[\w.]+', query.lower())
    if not words:
        return []
    now = time.time()
    for k in [k for k, v in FOUND.items() if now - v['t'] > TTL]:
        del FOUND[k]
    scored = []
    for it in _code_index():
        name = it['label'].lower()
        if not all(w in name for w in words):
            continue
        score = 50 - min(len(name), 40) * 0.5 + (60 if name == ' '.join(words) else 20 if name.startswith(words[0]) else 0)
        scored.append((-score, it))
    scored.sort(key=lambda x: x[0])
    out = []
    for _, it in scored[:limit]:
        token = secrets.token_hex(8)
        FOUND[token] = {'path': it['path'], 'label': it['label'], 't': now}
        out.append({'token': token, 'label': it['label'], 'where': it['path']})
    return out


def read_code(token):
    """The text of a file the creator agreed to show her: {'name', 'text', 'truncated'}. OSError when it is not allowed."""
    entry = FOUND.pop(token, None) if isinstance(token, str) else None
    if not entry or time.time() - entry['t'] > TTL:
        raise PermissionError('token')
    path = entry['path']
    low = os.path.basename(path).lower()
    if os.path.splitext(low)[1] not in CODE_EXT or SECRET_RE.search(low) or not os.path.isfile(path) or os.path.getsize(path) > MAX_READ_BYTES:
        raise OSError('file')
    if low.endswith('.log'):   # logs are read, never edited: no grant, secrets masked, long ones boiled down
        whole = _read(path, MAX_READ_BYTES)
        return {'name': entry['label'], 'text': digest_log(whole), 'truncated': False, 'digest': len(whole) > MAX_SEND_CHARS}
    text = _read(path, MAX_SEND_CHARS + 1)
    GRANTED[entry['label'].lower()] = {'path': path, 't': time.time()}
    for k in sorted(GRANTED, key=lambda k: GRANTED[k]['t'])[:-30]:
        del GRANTED[k]
    shown = text[:MAX_SEND_CHARS]
    check = infra.summary(path, shown)
    return {'name': entry['label'], 'text': shown + ('\n\n' + check if check else ''), 'truncated': len(text) > MAX_SEND_CHARS}


# ---- logs: a long log is boiled down to what matters, with secrets masked ----

LOG_BAD = re.compile(r'(?i)\b(fatal|critical|error|err|exception|traceback|panic|failed|failure|denied|timeout|timed out|refused|crash|'
                     r'segfault|assert|unhandled|warn(ing)?)\b|ошибк|сбой|исключени')
LOG_SECRET = re.compile(r'(?i)((?:password|passwd|pwd|secret|token|api[_-]?key|apikey|authorization|bearer|cookie|session)["\']?\s*[:=]?\s*"?(?:(?:bearer|basic)\s+)?)'
                        r'[^\s",;]{4,}|\b[A-Za-z0-9+/_-]{32,}={0,2}\b')
LOG_VOLATILE = re.compile(r'\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d+)?Z?|\b\d\d:\d\d:\d\d(?:[.,]\d+)?\b|0x[0-9a-fA-F]+|\b\d+\b')


def mask_secrets(text):
    return LOG_SECRET.sub(lambda m: (m.group(1) + '***') if m.group(1) else '***', text)


def digest_log(text, limit=MAX_SEND_CHARS):
    """A short picture of a log: size, the kinds of problem lines (the same line with other numbers counts once), the first
    place each one appeared with a few lines around it, and the very end of the log. A short log is returned as it is (secrets masked)."""
    text = mask_secrets(text)
    if len(text) <= limit:
        return text
    lines = text.splitlines()
    groups = {}
    for i, line in enumerate(lines):
        if LOG_BAD.search(line):
            key = LOG_VOLATILE.sub('#', line.strip())[:160]
            g = groups.setdefault(key, {'n': 0, 'first': i, 'last': i})
            g['n'] += 1
            g['last'] = i
    out = ['[Выжимка из длинного лога: %d строк, видов проблемных строк: %d. Ниже самое важное; всего лога ты не видишь.]' % (len(lines), len(groups))]
    ranked = sorted(groups.values(), key=lambda g: (-g['n'], g['first']))[:8]
    budget = limit // 2
    for g in sorted(ranked, key=lambda g: g['first']):
        chunk = '\n'.join(l[:240] for l in lines[max(0, g['first'] - 2):g['first'] + 4])
        piece = '\n— встретилось %d раз(а), строки %d–%d:\n%s' % (g['n'], g['first'] + 1, g['last'] + 1, chunk)
        if len(piece) > budget:
            break
        budget -= len(piece)
        out.append(piece)
    out.append('\n— Конец лога (последние строки):\n' + '\n'.join(l[:240] for l in lines[-25:]))
    return '\n'.join(out)[:limit]


def start():
    """Scan in the background at launch so that answers about the computer are instant later."""
    threading.Thread(target=lambda: (scan(), _code_index()), daemon=True).start()
