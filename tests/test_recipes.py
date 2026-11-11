"""Recipes (recipes.py): every operation passes the bridge's own validator; chunks of three; triggers in ru/en/ko/ja; 'next' only mid-recipe."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.skills import recipes
from luna.dev import godot_bridge
from luna.dev import unity_bridge
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

for (engine, kind), (title, ops) in recipes.RECIPES.items():
    bridge = godot_bridge if engine == 'godot' else unity_bridge
    bad = []
    for o in ops:
        try:
            bridge.parse(o)
        except ValueError:
            bad.append(o)
    ok('%s/%s: every op valid %s' % (engine, kind, bad), not bad)
    scenes = [o.split()[1] for o in ops if o.startswith('scene ')]
    ok('%s/%s: starts with a scene' % (engine, kind), ops[0].startswith('scene '))
    used = {o.split()[1] for o in ops if o.split()[0] in ('node', 'object', 'attach', 'move', 'text')}
    ok('%s/%s: ops use only the created scene' % (engine, kind), used <= set(scenes))
    ok('%s/%s: scripts attached are created first' % (engine, kind), all(any(c.startswith('script ' + a.split()[3]) for c in ops[:i]) for i, a in enumerate(ops) if a.startswith('attach ')))

cases = [('сделай платформер в Godot', 'godot', 'platformer'), ('создай 3D сцену в Юнити', 'unity', 'scene3d'), ('build a top-down game in Godot', 'godot', 'topdown'),
         ('make a main menu in Godot', 'godot', 'menu'), ('고도로 플랫포머 만들어줘', 'godot', 'platformer'), ('유니티로 3D 씬 만들어줘', 'unity', 'scene3d'),
         ('Godotでメニューを作って', 'godot', 'menu'), ('ユニティで3Dシーンを作りたい', 'unity', 'scene3d'), ('хочу 2D игру в Godot', 'godot', 'platformer')]
for text, e, k in cases:
    recipes.STATE.update(key=None, pos=0)
    ok('picked: ' + text, recipes._pick(text) == (e, k))
for text in ['сделай платформер', 'как дела в Godot', 'расскажи про Unity', 'make a sandwich', '']:
    recipes.STATE.update(key=None, pos=0)
    ok('not a recipe: ' + text, recipes.hint(text) == '')

recipes.STATE.update(key=None, pos=0)
ok('"дальше" is silent without a recipe', recipes.hint('дальше') == '')
h1 = recipes.hint('сделай платформер в Godot')
ok('first chunk has exactly three tags', len(re.findall(r'\[gd:', h1)) == 3 and 'scene Main 2d' in h1)
h2 = recipes.hint('дальше')
ok('second chunk continues', 'script Player platformer2d' in h2 and 'шаг 4-6' in h2)
h3 = recipes.hint('next')
ok('third chunk', 'play' in h3 and 'Camera2D' in h3)
ok('recipe ends and resets', recipes.STATE['key'] is None and recipes.hint('дальше') == '')
ok('last chunk says all built', 'последний шаг' in h3)
ok('unity tags', '[unity:scene Main 3d]' in recipes.hint('create a 3D scene in Unity'))
for word in ('다음', '次', 'continue', 'продолжай'):
    recipes.STATE.update(key=('godot', 'menu'), pos=3)
    ok('next word: ' + word, '[gd:' in recipes.hint(word))
recipes.STATE.update(key=('godot', 'menu'), pos=3)
ok('long sentence is not "next"', recipes.hint('дальше расскажи про погоду в Москве сегодня') == '')
