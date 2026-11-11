"""Build recipes for the engines she has hands in (Godot, Unity): "сделай платформер в Godot", "build a 3D scene in Unity", "고도로 메뉴 만들어줘", "Godotでメニューを作って".
A recipe is a fixed list of operations from the bridges' own vocabulary; every one is checked by the bridge's parse() in the tests, so the model never invents a command. Only three operations
fit in one reply, so the program hands her the next three and remembers the place ("дальше" / "next" / "다음" / "次" moves on). Each operation still waits for his press on a plate."""
import re

CHUNK = 3
ENGINES = {'godot': r'godot|годот|고도|ゴドー|ゴドット', 'unity': r'unity|юнити|유니티|ユニティ'}
RECIPES = {
    ('godot', 'platformer'): ('2D-платформер', ['scene Main 2d', 'node Main CharacterBody2D Player 100 100', 'node Main CollisionShape2D PlayerShape 100 100', 'script Player platformer2d',
                                                'attach Main Player Player', 'node Main StaticBody2D Ground 100 300', 'node Main CollisionShape2D GroundShape 100 300',
                                                'node Main Camera2D Cam 100 100', 'play']),
    ('godot', 'topdown'): ('2D-игра с видом сверху', ['scene Main 2d', 'node Main CharacterBody2D Hero 200 200', 'node Main Sprite2D HeroSprite 200 200', 'script Hero topdown2d',
                                                      'attach Main Hero Hero', 'node Main Camera2D Cam 200 200', 'script Cam follow_camera2d', 'attach Main Cam Cam', 'play']),
    ('godot', 'scene3d'): ('3D-сцена с героем', ['scene World 3d', 'node World DirectionalLight3D Sun 0 5 0', 'node World Camera3D Cam 0 2 6', 'node World MeshInstance3D Floor 0 0 0',
                                                 'node World CharacterBody3D Player 0 1 0', 'script Player mover3d', 'attach World Player Player', 'node World MeshInstance3D Box 3 0.5 0', 'play']),
    ('godot', 'menu'): ('главное меню', ['scene Menu ui', 'node Menu Label Title', 'text Menu Title My game', 'node Menu Button Start', 'text Menu Start Play', 'node Menu Button Quit',
                                         'text Menu Quit Exit']),
    ('unity', 'scene3d'): ('3D-сцена с героем', ['scene Main 3d', 'object Main plane Floor 0 0 0', 'object Main light Sun 0 5 0', 'object Main camera Cam 0 2 -6', 'object Main capsule Player 0 1 0',
                                                 'script Player mover3d', 'attach Main Player Player', 'object Main cube Box 0 0.5 2', 'play']),
    ('unity', 'platformer'): ('2D-сцена с героем', ['scene Main 2d', 'object Main sprite Player 0 0', 'script Player mover2d', 'attach Main Player Player', 'object Main camera Cam 0 0',
                                                    'script Cam follow', 'attach Main Cam Cam', 'play']),
}
_KIND = {'platformer': r'платформер|platformer|플랫포머|プラットフォーマー',
         'topdown': r'сверху|top[- ]?down|탑다운|トップダウン',
         'scene3d': r'3d|3д|трёхмерн|трехмерн|3차원|3\s*d\s*씬|3\s*次元',
         'menu': r'меню|\bmenu\b|메뉴|メニュー'}
_BUILD = re.compile(r'(?i)сдела|созда|собер|собра|построй|набросай|настро|хочу|make|build|create|set up|scaffold|start a|만들|구성|시작|作って|作成|作りたい|始め|つくって')
_NEXT = re.compile(r'(?i)^\W*(?:дальше|продолжай|продолжи|далее|ещё|еще|следующ\w*|next|continue|go on|more|다음|계속|次|続けて|つづけて)\W*$')
STATE = {'key': None, 'pos': 0}


def _pick(text):
    text = str(text or '')[:300]
    if not _BUILD.search(text):
        return None
    engine = next((e for e, rx in ENGINES.items() if re.search('(?i)' + rx, text)), None)
    if not engine:
        return None
    for kind, rx in _KIND.items():
        if re.search('(?i)' + rx, text) and (engine, kind) in RECIPES:
            return (engine, kind)
    if re.search('(?i)2d|2д|2차원|2次元', text) and (engine, 'platformer') in RECIPES:
        return (engine, 'platformer')
    return None


def _chunk(key):
    title, ops = RECIPES[key]
    start = STATE['pos']
    part = ops[start:start + CHUNK]
    STATE['pos'] = start + len(part)
    tag = 'gd' if key[0] == 'godot' else 'unity'
    done = STATE['pos'] >= len(ops)
    tags = ' '.join('[%s:%s]' % (tag, o) for o in part)
    if done:
        STATE['key'], STATE['pos'] = None, 0
    return ('[Он хочет построить в %s: %s. Это готовый проверенный рецепт, шаг %d-%d из %d. В этой реплике поставь РОВНО эти команды, по порядку, дословно: %s. '
            'Каждая сработает после его нажатия на плашке. %s Не придумывай других команд.]'
            % ('Godot' if key[0] == 'godot' else 'Unity', title, start + 1, start + len(part), len(ops), tags,
               'Это последний шаг: скажи, что всё собрано и что можно запускать.' if done else 'Скажи, что остальное доделаете дальше: он может написать «дальше».'))


def hint(text):
    """The next chunk of a recipe when he asks to build something (or says 'next' mid-recipe); '' otherwise."""
    key = _pick(text)
    if key:
        STATE['key'], STATE['pos'] = key, 0
        return _chunk(key)
    if STATE['key'] and _NEXT.match(str(text or '')[:60]):
        return _chunk(STATE['key'])
    return ''
