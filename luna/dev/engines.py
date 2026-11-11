"""Game engines and frameworks beyond the three she has hands in (Unreal, Unity, Godot): a catalog of about thirty, what each one's project looks like, which language it
uses, how it is run and built, and the usual traps. Two uses, both read-only:
1. facts: when he names an engine ("как запустить игру на Defold", "what language does GameMaker use", "ゲームメーカー", "게임메이커"), the program hands her a short true note
   instead of letting her guess from memory;
2. analysis: "проанализируй проект", "analyze my project", "프로젝트 분석해줘", "プロジェクトを分析して" looks at one project folder he has (a found project, one of his workspaces,
   or a folder he names in quotes) and reports the engine, the code by language, scenes, assets, the biggest and the freshest files and the TODO count. Only relative file names
   go into the note, never absolute paths and never file contents.
She can build things by hand only in Unreal, Unity and Godot; for every other engine she says so honestly and helps by reading, advising and giving code in a block."""
import json
import os
import re

HANDS = ('unreal', 'unity', 'godot')

# key: (name, language, run, build, notes, aliases regex)
CATALOG = {
    'unreal': ('Unreal Engine', 'C++ и Blueprints (Python только в редакторе)', 'открыть .uproject в редакторе, Play', 'File > Package Project',
               'первая сборка C++ долгая; проект открывается только нужной версией движка', r'unreal|анр[еи]а?л|унр[еи]а?л|언리얼|アンリアル'),
    'unity': ('Unity', 'C#', 'открыть папку в Unity Hub, Play', 'File > Build Settings', 'сцены в Assets/Scenes; скрипт и класс должны называться одинаково; папка Library пересоздаётся сама',
              r'unity|юнити|유니티|ユニティ'),
    'godot': ('Godot', 'GDScript (и C#)', 'godot --path <папка> или кнопка Play в редакторе', 'Project > Export (нужны шаблоны экспорта)',
              'сцены .tscn и скрипты .gd лежат прямо в проекте; папка .godot служебная', r'godot|годот|고도|ゴドー|ゴドット|gdscript'),
    'gamemaker': ('GameMaker', 'GML', 'кнопка Run в IDE (или командная строка Igor)', 'Create Executable в меню Build', 'проект это файл .yyp и папки объектов, комнат и скриптов; правка .yy-файлов руками хрупкая, лучше через IDE',
                  r'game ?maker|гейм ?мейкер|гамемейкер|게임 ?메이커|ゲームメーカー|\bgml\b'),
    'defold': ('Defold', 'Lua', 'Project > Build в редакторе (или bob.jar)', 'Project > Bundle', 'проект описан в game.project; логика в .script, интерфейс в .gui_script, сборки лёгкие и для веба тоже',
               r'defold|дефолд|디폴드|デフォルド'),
    'cocos': ('Cocos Creator', 'TypeScript', 'Preview в редакторе Cocos Creator', 'Project > Build', 'версия редактора важна: проекты разных версий не открываются друг в друге; код в assets/', r'cocos|кокос|코코스|ココス'),
    'love2d': ('LÖVE (LOVE2D)', 'Lua', 'love . в папке проекта', 'упаковать папку в .love и склеить с love.exe', 'точка входа main.lua, настройки окна в conf.lua; редактора нет, это просто библиотека',
               r'l[öo]ve ?2?d|\blove2d\b|лёве|лове2д|뢰브|ラブ2d'),
    'solar2d': ('Solar2D', 'Lua', 'Solar2D Simulator открывает main.lua', 'File > Build', 'рядом с main.lua лежат build.settings и config.lua', r'solar ?2d|corona ?sdk|солар'),
    'bevy': ('Bevy', 'Rust', 'cargo run', 'cargo build --release', 'ECS без редактора; первая компиляция очень долгая, включай dynamic_linking только для разработки', r'\bbevy\b|бэви|бевi|베비|ベヴィ'),
    'fyrox': ('Fyrox', 'Rust', 'cargo run (или редактор fyroxed)', 'cargo build --release', 'есть собственный редактор сцен', r'fyrox|фирокс'),
    'macroquad': ('Macroquad', 'Rust', 'cargo run', 'cargo build --release', 'очень лёгкий 2D-фреймворк, ничего лишнего', r'macroquad|ggez'),
    'monogame': ('MonoGame', 'C#', 'dotnet run', 'dotnet publish', 'ресурсы собирает Content.mgcb через Content Pipeline: новый файл нужно добавить туда', r'mono ?game|моногейм|모노게임|モノゲーム|\bxna\b'),
    'stride': ('Stride', 'C#', 'Game Studio, кнопка Run', 'Build в Game Studio', 'проект .sdpkg, редактор Game Studio только под Windows', r'\bstride\b|страйд'),
    'flax': ('Flax Engine', 'C# и C++', 'открыть .flaxproj в Flax Editor', 'File > Build game', 'похож на Unreal по духу, лёгкий по размеру', r'flax|флакс'),
    'o3de': ('O3DE', 'C++ и Lua', 'Project Manager, затем Editor', 'cmake сборка из консоли', 'тяжёлый: нужны Visual Studio и CMake, сборка идёт долго', r'o3de|open 3d engine'),
    'rpgmaker': ('RPG Maker', 'JavaScript (плагины)', 'Test Play в редакторе', 'Deployment', 'данные в data/*.json, плагины в js/plugins; файлы данных руками не правь', r'rpg ?maker|рпг ?мейкер|rpg ?쯔꾸르|rpgツクール|ツクール|쯔꾸르'),
    'renpy': ("Ren'Py", 'Python и язык .rpy', 'Ren\'Py Launcher: Launch Project', 'Build Distributions в лаунчере', 'сценарий в game/script.rpy; отступы пробелами, как в Python', r"ren'?py|рен'?пи|ренпай|렌파이|レンパイ"),
    'construct': ('Construct', 'визуальные события и JS', 'Preview в редакторе (в браузере)', 'Export', 'проект .c3p; работает в браузере, поэтому код и ресурсы проще всего править в самом редакторе', r'construct ?[23]|конструкт|컨스트럭트|コンストラクト'),
    'gdevelop': ('GDevelop', 'визуальные события и JS', 'Preview в редакторе', 'Export / Publish', 'всё хранится в одном json-файле проекта, не правь его руками', r'gdevelop|гдевелоп|지디벨롭|ジーディベロップ'),
    'phaser': ('Phaser', 'JavaScript и TypeScript', 'npm run dev (или любой локальный сервер)', 'npm run build', 'ресурсы нужно грузить в preload, а открывать index.html двойным кликом нельзя: нужен сервер', r'phaser|фэйзер|фейзер|페이저|フェイザー'),
    'pixi': ('PixiJS', 'JavaScript и TypeScript', 'npm run dev', 'npm run build', 'это только рендер, физику и сцены придётся брать отдельно', r'pixi ?js|\bpixi\b|пикси'),
    'three': ('three.js', 'JavaScript и TypeScript', 'npm run dev', 'npm run build', 'это библиотека 3D, а не движок: игровой цикл, физика и ввод свои', r'three\.?js|тре[её]х ?js|스리제이에스'),
    'babylon': ('Babylon.js', 'JavaScript и TypeScript', 'npm run dev', 'npm run build', 'есть своя физика и инспектор сцены', r'babylon|бабилон'),
    'playcanvas': ('PlayCanvas', 'JavaScript', 'Launch в веб-редакторе', 'Publish в веб-редакторе', 'проект живёт на сервере PlayCanvas, локально только скрипты', r'playcanvas|плейканвас'),
    'pygame': ('Pygame', 'Python', 'python main.py', 'pyinstaller', 'своего редактора нет; следи за частотой кадров через pygame.time.Clock', r'pygame|пигейм|파이게임|パイゲーム'),
    'libgdx': ('libGDX', 'Java и Kotlin', 'gradlew desktop:run', 'gradlew desktop:dist', 'проект многомодульный (core, desktop, android), игровой код в core', r'libgdx|либгдх'),
    'raylib': ('raylib', 'C и C++', 'сборка через CMake или makefile', 'cmake --build', 'лёгкая библиотека без редактора; есть привязки почти ко всем языкам', r'raylib|рейлиб|레이라이브'),
    'haxe': ('Haxe (Heaps, HaxeFlixel, OpenFL)', 'Haxe', 'lime test <цель> или hl', 'lime build <цель>', 'сборка идёт через lime/hxml; цель выбирают при запуске', r'haxeflixel|flixel|heaps\.io|\bheaps\b|openfl|\bhaxe\b'),
    'ags': ('Adventure Game Studio', 'AGS Script (похож на C)', 'Run в редакторе AGS', 'Build EXE', 'точечные приключения, редактор только под Windows', r'adventure game studio|\bags\b'),
    'pico8': ('PICO-8', 'Lua', 'load и run в консоли PICO-8', 'export', 'жёсткие лимиты: 8192 токена, 128x128 пикселей, 16 цветов', r'pico-?8'),
    'roblox': ('Roblox', 'Luau', 'Play в Roblox Studio', 'Publish в Roblox', 'серверные и клиентские скрипты разделены; с папкой можно работать через Rojo', r'roblox|роблокс|로블록스|ロブロックス|\brojo\b'),
}

_CODE = {'.gd': 'GDScript', '.cs': 'C#', '.cpp': 'C++', '.cc': 'C++', '.h': 'C/C++ заголовки', '.hpp': 'C/C++ заголовки', '.c': 'C', '.py': 'Python', '.lua': 'Lua', '.js': 'JavaScript',
         '.ts': 'TypeScript', '.tsx': 'TypeScript', '.jsx': 'JavaScript', '.rs': 'Rust', '.java': 'Java', '.kt': 'Kotlin', '.gml': 'GML', '.rpy': "Ren'Py", '.hx': 'Haxe', '.script': 'Defold script',
         '.gui_script': 'Defold GUI script', '.shader': 'шейдеры', '.gdshader': 'шейдеры', '.glsl': 'шейдеры', '.hlsl': 'шейдеры', '.usf': 'шейдеры', '.cginc': 'шейдеры', '.luau': 'Luau', '.agf': 'AGS'}
_SCENE = {'.tscn', '.unity', '.umap', '.scn', '.prefab', '.fire', '.room', '.yy', '.c3p', '.map', '.level', '.tres'}
_IMAGE = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tga', '.psd', '.svg', '.gif', '.dds', '.exr', '.ase', '.aseprite'}
_AUDIO = {'.wav', '.ogg', '.mp3', '.flac', '.opus', '.mid'}
_MODEL = {'.fbx', '.obj', '.gltf', '.glb', '.blend', '.dae', '.uasset', '.3ds'}
_SKIP = {'.git', '.svn', 'node_modules', 'library', 'temp', 'obj', 'bin', 'binaries', 'intermediate', 'saved', '.godot', '.import', 'deriveddatacache', '__pycache__', '.venv', 'venv',
         'target', 'build', 'builds', 'dist', '.idea', '.vs', 'logs', '.luna_backup', 'packages'}
MAX_FILES, MAX_DEPTH, MAX_READ = 6000, 8, 120000


def _read(path, limit=60000):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read(limit)
    except OSError:
        return ''


def _top(path):
    try:
        return {e.name.lower(): e.is_dir() for e in os.scandir(path)}
    except OSError:
        return {}


def detect(path):
    """Engines whose project lives in this folder: [{'engine', 'version'}], best first. Reads only the top level and a few small marker files."""
    names = _top(path)
    files = [n for n, d in names.items() if not d]
    found = []

    def add(key, version=''):
        if key not in [f['engine'] for f in found]:
            found.append({'engine': key, 'version': version})
    for n in files:
        if n.endswith('.uproject'):
            try:
                ver = str(json.loads(_read(os.path.join(path, n), 20000)).get('EngineAssociation') or '')
            except ValueError:
                ver = ''
            add('unreal', ver)
        elif n == 'project.godot':
            m = re.search(r'config/features=.*?"(\d+\.\d+)"', _read(os.path.join(path, n), 20000))
            add('godot', m.group(1) if m else '')
        elif n.endswith('.yyp'):
            add('gamemaker')
        elif n == 'game.project':
            add('defold')
        elif n.endswith('.mgcb'):
            add('monogame')
        elif n.endswith('.sdpkg'):
            add('stride')
        elif n.endswith('.flaxproj'):
            add('flax')
        elif n.endswith(('.agf',)):
            add('ags')
        elif n.endswith('.p8'):
            add('pico8')
        elif n.endswith(('.c3p', '.c3proj')):
            add('construct')
        elif n.endswith(('.rpgproject', '.rmmzproject', '.rmmvproject')) or n in ('game.rpgproject',):
            add('rpgmaker')
        elif n == 'default.project.json' or n.endswith(('.rbxl', '.rbxlx')):
            add('roblox')
        elif n.endswith('.hxml') or n == 'project.xml':
            blob = _read(os.path.join(path, n), 20000).lower()
            if any(k in blob for k in ('flixel', 'heaps', 'openfl', 'lime', 'haxe')) or n.endswith('.hxml'):
                add('haxe')
        elif n == 'project.json':
            blob = _read(os.path.join(path, n), 20000).lower()
            if 'o3de' in blob:
                add('o3de')
            elif 'creator' in blob:
                add('cocos')
        elif n == 'cargo.toml':
            blob = _read(os.path.join(path, n), 20000).lower()
            for key in ('bevy', 'fyrox', 'macroquad', 'ggez'):
                if re.search(r'^\s*%s\b|\b%s\s*=' % (key, key), blob, re.M):
                    add('macroquad' if key == 'ggez' else key)
        elif n == 'package.json':
            blob = _read(os.path.join(path, n), 20000).lower()
            for key, dep in (('phaser', '"phaser"'), ('pixi', '"pixi.js"'), ('three', '"three"'), ('babylon', '"@babylonjs/'), ('playcanvas', '"playcanvas"'), ('cocos', '"cc"')):
                if dep in blob:
                    add(key)
            if '"gdevelop' in blob:
                add('gdevelop')
        elif n in ('build.gradle', 'build.gradle.kts', 'settings.gradle'):
            if re.search(r'libgdx|com\.badlogicgames', _read(os.path.join(path, n), 20000).lower()):
                add('libgdx')
        elif n.endswith('.csproj'):
            if 'monogame' in _read(os.path.join(path, n), 20000).lower():
                add('monogame')
        elif n == 'cmakelists.txt':
            if 'raylib' in _read(os.path.join(path, n), 20000).lower():
                add('raylib')
    if names.get('projectsettings') and names.get('assets'):
        m = re.search(r'm_EditorVersion:\s*(\S+)', _read(os.path.join(path, 'ProjectSettings', 'ProjectVersion.txt'), 4000))
        if m:
            add('unity', m.group(1))
    if names.get('game') is True and any(os.path.isfile(os.path.join(path, 'game', f)) for f in ('script.rpy', 'options.rpy')):
        add('renpy')
    if 'main.lua' in files:
        if 'build.settings' in files:
            add('solar2d')
        elif 'conf.lua' in files:
            add('love2d')
    if names.get('js') is True and any(os.path.isfile(os.path.join(path, 'js', f)) for f in ('rmmz_core.js', 'rpg_core.js')):
        add('rpgmaker')
    if not found:
        for n in files:
            if n.endswith('.py') and re.search(r'^\s*(?:import|from)\s+pygame\b', _read(os.path.join(path, n), 30000), re.M):
                add('pygame')
                break
    return found


def info(key):
    return CATALOG.get(key)


def facts_line(key, version=''):
    name, lang, run, build, notes, _ = CATALOG[key]
    hands = 'руками в нём она умеет строить (после нажатия «Сделать»)' if key in HANDS else 'руками в нём она работать не умеет: читает, советует и даёт код блоком, правки он вносит сам'
    return '%s%s: язык %s; запуск: %s; сборка: %s; важно: %s; %s' % (name, ' ' + version if version else '', lang, run, build, notes, hands)


def _edge(pattern):
    """\\b does not see a boundary between a Latin word and Hangul/Kana (all are word characters), so use ASCII lookarounds instead."""
    pattern = re.sub(r'\\b(?=[A-Za-z(])', '(?<![A-Za-z0-9_])', pattern)
    return pattern.replace(r'\b', '(?![A-Za-z0-9_])')


_MENTION = {k: re.compile('(?i)' + _edge(v[5])) for k, v in CATALOG.items() if k not in HANDS}
_ASKING = re.compile(r'(?i)\?|как |что |чем |какой|какая|какие|на каком|почему|стоит ли|посоветуй|подскажи|сравни|\bhow\b|\bwhat\b|\bwhich\b|\bwhy\b|should i|recommend|compare|어떻|무슨|뭐|왜|추천|どう|何|なぜ|おすすめ|比較')


def mention_hint(text):
    """Facts for her when he asks about an engine that has no hands: up to two engines, once per message."""
    text = str(text or '')[:300]
    if not _ASKING.search(text):
        return ''
    keys = [k for k, rx in _MENTION.items() if rx.search(text)][:2]
    if not keys:
        return ''
    return ('[Он говорит о движке или фреймворке, и вот проверенные факты о нём (опирайся на них, не выдумывай сверх них, а чего не знаешь, признай): %s.]'
            % ' | '.join(facts_line(k) for k in keys))


# ---- analysis of one project folder ----
def analyze(path):
    """A read-only look at a project folder: {'engines', 'files', 'code', 'scenes', 'images', 'audio', 'models', 'bytes', 'biggest', 'newest', 'todo', 'entry'}; relative names only."""
    path = os.path.abspath(path)
    out = {'engines': detect(path), 'files': 0, 'code': {}, 'scenes': 0, 'images': 0, 'audio': 0, 'models': 0, 'bytes': 0, 'biggest': [], 'newest': [], 'todo': 0, 'entry': [], 'cut': False}
    seen, read_total, code_files = [], 0, []
    stack = [(path, 0)]
    while stack and out['files'] < MAX_FILES:
        base, depth = stack.pop()
        try:
            entries = sorted(os.scandir(base), key=lambda e: e.name.lower())
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if e.name.lower() not in _SKIP and not e.name.startswith('.') and depth < MAX_DEPTH:
                        stack.append((e.path, depth + 1))
                    continue
                if e.is_symlink():
                    continue
                st = e.stat()
            except OSError:
                continue
            out['files'] += 1
            out['bytes'] += st.st_size
            rel = os.path.relpath(e.path, path).replace('\\', '/')
            ext = os.path.splitext(e.name)[1].lower()
            seen.append((st.st_size, st.st_mtime, rel))
            if ext in _CODE:
                out['code'][_CODE[ext]] = out['code'].get(_CODE[ext], 0) + 1
                if ext not in ('.shader', '.gdshader', '.glsl', '.hlsl', '.usf', '.cginc', '.h', '.hpp'):
                    code_files.append(e.path)
                if re.match(r'(?i)^(main|game|app|index|program)\.', e.name) and len(out['entry']) < 4:
                    out['entry'].append(rel)
            elif ext in _SCENE:
                out['scenes'] += 1
            elif ext in _IMAGE:
                out['images'] += 1
            elif ext in _AUDIO:
                out['audio'] += 1
            elif ext in _MODEL:
                out['models'] += 1
    out['cut'] = out['files'] >= MAX_FILES
    out['biggest'] = [r for _, _, r in sorted(seen, reverse=True)[:5]]
    out['newest'] = [r for _, _, r in sorted(seen, key=lambda s: s[1], reverse=True)[:5]]
    for fp in code_files[:300]:
        if read_total > MAX_READ * 8:
            break
        blob = _read(fp, MAX_READ)
        read_total += len(blob)
        out['todo'] += len(re.findall(r'\b(?:TODO|FIXME|HACK)\b', blob))
    return out


def _size(n):
    for unit in ('Б', 'КБ', 'МБ', 'ГБ'):
        if n < 1024 or unit == 'ГБ':
            return '%d %s' % (n, unit) if unit == 'Б' else '%.1f %s' % (n, unit)
        n /= 1024.0


def report_text(name, a):
    parts = []
    if a['engines']:
        parts.append('движок: ' + ', '.join(CATALOG[e['engine']][0] + (' ' + e['version'] if e['version'] else '') for e in a['engines']))
    else:
        parts.append('движок по файлам не определился (возможно, это папка с ресурсами, нестандартный движок или папка выше проекта)')
    parts.append('файлов %d%s, вес %s' % (a['files'], ' (посчитаны первые %d)' % MAX_FILES if a['cut'] else '', _size(a['bytes'])))
    if a['code']:
        parts.append('код: ' + ', '.join('%s %d' % (k, v) for k, v in sorted(a['code'].items(), key=lambda kv: -kv[1])[:6]))
    bits = [s for s in ('сцен и уровней %d' % a['scenes'] if a['scenes'] else '', 'картинок %d' % a['images'] if a['images'] else '', 'звуков %d' % a['audio'] if a['audio'] else '',
                        '3D-моделей %d' % a['models'] if a['models'] else '') if s]
    if bits:
        parts.append(', '.join(bits))
    if a['entry']:
        parts.append('вероятные точки входа: ' + ', '.join(a['entry']))
    if a['biggest']:
        parts.append('самые тяжёлые файлы: ' + ', '.join(a['biggest']))
    if a['newest']:
        parts.append('менялись последними: ' + ', '.join(a['newest']))
    if a['todo']:
        parts.append('пометок TODO/FIXME в коде: %d' % a['todo'])
    facts = ' | '.join(facts_line(e['engine'], e['version']) for e in a['engines'][:2])
    return ('[Программа осмотрела проект «%s» (только чтение, содержимое файлов не читалось, кроме подсчёта TODO). %s.%s Перескажи коротко и по делу, посоветуй, с чего начать; '
            'называй только файлы из этого списка, ничего не выдумывай.]' % (name, '; '.join(parts), (' Факты о движке: ' + facts + '.') if facts else ''))


# ---- which project ----
_ASK_ANALYZE = re.compile(r'(?i)(?:проанализируй|разбери|осмотри|изучи|посмотри|оцени|обзор|расскажи про)\s+(?:мой |мою |наш |нашу |этот |эту |весь |всю )?(?:проект|игру)|что (?:у меня )?в (?:моём |моем |этом )?проекте|'
                          r'(?:analy[sz]e|review|inspect|look at|scan|overview of)\s+(?:my |our |this |the )?(?:project|game)|what.?s in (?:my |this |the )?project|project overview|'
                          r'프로젝트\s*(?:를|을)?\s*(?:분석|살펴|검토|훑어)|내 프로젝트.{0,6}(?:뭐|분석)|'
                          r'プロジェクトを?\s*(?:分析|調べ|確認|見て|チェック)')
_QUOTED = re.compile(r'["«“]([^"»”]{3,200})["»”]')


def wants_analysis(text):
    return bool(_ASK_ANALYZE.search(str(text or '')[:300]))


def _candidates(extra=None):
    out = []
    try:
        from luna.dev import devtools
        for p in devtools.projects():
            out.append((p.get('name') or os.path.basename(p['root']), p['root']))
    except Exception:
        pass
    try:
        from luna.hands import projects
        for w in projects.workspaces():
            if isinstance(w, dict) and w.get('path'):
                out.append((w.get('name') or os.path.basename(w['path']), w['path']))
    except Exception:
        pass
    for item in extra or []:
        out.append(item)
    seen, uniq = set(), []
    for name, root in out:
        key = os.path.normcase(os.path.abspath(str(root)))
        if key not in seen and os.path.isdir(root):
            seen.add(key)
            uniq.append((str(name), str(root)))
    return uniq


def analysis_hint(text, extra=None):
    """The note for her with the report of the project he means, or a plain question which one; '' if he did not ask for an analysis."""
    if not wants_analysis(text):
        return ''
    text = str(text or '')
    for q in _QUOTED.findall(text):
        q = q.strip()
        if os.path.isabs(q) and os.path.isdir(q):
            return report_text(os.path.basename(os.path.normpath(q)) or q, analyze(q))
    cands = _candidates(extra)
    low = text.lower()
    named = [c for c in cands if len(c[0]) >= 3 and c[0].lower() in low]
    if len(named) == 1:
        return report_text(named[0][0], analyze(named[0][1]))
    if len(cands) == 1:
        return report_text(cands[0][0], analyze(cands[0][1]))
    if not cands:
        return ('[Он просит разобрать проект, но программа не знает ни одной его папки с проектом. Скажи об этом честно: пусть назовёт полный путь к папке проекта в кавычках '
                '(«проанализируй проект "D:\\\\Games\\\\Мой"») или добавит её как рабочую папку. Ничего не придумывай про его проект.]')
    return ('[Он просит разобрать проект, но их несколько: %s. Спроси, какой именно (пусть назовёт имя), ничего не выдумывай.]' % ', '.join(c[0] for c in (named or cands)[:8]))
