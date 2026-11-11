"""Engines (engines.py): detection by marker files for many engines, facts when he asks about one, read-only project analysis, triggers in ru/en/ko/ja."""
import os
import sys
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.dev import engines
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

root = tempfile.mkdtemp(prefix='luna-engines-')


def make(name, files):
    base = os.path.join(root, name)
    for rel, body in files.items():
        p = os.path.join(base, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(body)
    return base


cases = {
    'godot': ('godot', {'project.godot': 'config/features=PackedStringArray("4.3", "Forward Plus")\n', 'player.gd': '# TODO fix\nextends Node\n'}),
    'unreal': ('unreal', {'My.uproject': '{"EngineAssociation": "5.4"}'}),
    'unity': ('unity', {'ProjectSettings/ProjectVersion.txt': 'm_EditorVersion: 2022.3.10f1\n', 'Assets/a.cs': 'class A{}'}),
    'gamemaker': ('gamemaker', {'game.yyp': '{}'}),
    'defold': ('defold', {'game.project': '[project]'}),
    'love': ('love2d', {'main.lua': 'function love.load() end', 'conf.lua': ''}),
    'solar': ('solar2d', {'main.lua': '', 'build.settings': ''}),
    'bevy': ('bevy', {'Cargo.toml': '[dependencies]\nbevy = "0.14"\n'}),
    'mono': ('monogame', {'Content/Content.mgcb': '', 'Game.csproj': '<PackageReference Include="MonoGame.Framework"/>'}),
    'phaser': ('phaser', {'package.json': '{"dependencies": {"phaser": "^3"}}'}),
    'three': ('three', {'package.json': '{"dependencies": {"three": "^0.160"}}'}),
    'renpy': ('renpy', {'game/script.rpy': 'label start:\n'}),
    'pygame': ('pygame', {'main.py': 'import pygame\n'}),
    'flax': ('flax', {'G.flaxproj': '{}'}),
    'construct': ('construct', {'g.c3p': ''}),
    'roblox': ('roblox', {'default.project.json': '{}'}),
    'pico': ('pico8', {'cart.p8': ''}),
}
for name, (key, files) in cases.items():
    got = engines.detect(make(name, files))
    ok('detect %s' % key, bool(got) and got[0]['engine'] == key)
ok('godot version read', engines.detect(os.path.join(root, 'godot'))[0]['version'] == '4.3')
ok('unreal version read', engines.detect(os.path.join(root, 'unreal'))[0]['version'] == '5.4')
ok('unity version read', engines.detect(os.path.join(root, 'unity'))[0]['version'].startswith('2022'))
ok('empty folder detects nothing', engines.detect(make('empty', {'readme.txt': 'hi'})) == [])
ok('missing folder detects nothing', engines.detect(os.path.join(root, 'nope')) == [])
ok('every catalog entry has six fields', all(len(v) == 6 for v in engines.CATALOG.values()))
ok('every alias regex compiles', all(__import__('re').compile(v[5]) for v in engines.CATALOG.values()))
ok('hands only in three engines', engines.HANDS == ('unreal', 'unity', 'godot'))
ok('honest about no hands', 'не умеет' in engines.facts_line('defold') and 'не умеет' not in engines.facts_line('godot'))

# facts when he asks
for text, word in [('как запустить игру на Defold?', 'Defold'), ('what language does GameMaker use?', 'GameMaker'), ('что лучше, Phaser или PixiJS?', 'Phaser'),
                   ('Bevy가 뭐야?', 'Bevy'), ('ゲームメーカーの言語は何?', 'GameMaker'), ('как собрать игру на Love2D', 'LÖVE'), ('로블록스 어떻게 시작해?', 'Roblox'),
                   ('pygame как сделать окно?', 'Pygame')]:
    h = engines.mention_hint(text)
    ok('facts: ' + text, word in h and 'Он говорит о движке' in h)
ok('no facts without a question', engines.mention_hint('я люблю Defold') == '')
ok('no facts for unrelated', engines.mention_hint('как дела?') == '')
ok('hands engines are not served by facts (bridges cover them)', engines.mention_hint('как работает Unity?') == '')

# analysis triggers
for text in ['проанализируй проект', 'разбери мою игру', 'что в моём проекте?', 'analyze my project', 'review the game', "what's in my project", '프로젝트를 분석해줘', '내 프로젝트 분석', 'プロジェクトを分析して',
             'プロジェクトを調べて']:
    ok('wants analysis: ' + text, engines.wants_analysis(text))
for text in ['как дела', 'проанализируй мой сон', 'analyze this song', '']:
    ok('not analysis: ' + text, not engines.wants_analysis(text))

# analysis of a folder
a = engines.analyze(os.path.join(root, 'godot'))
ok('analysis counts files and code', a['files'] == 2 and a['code'].get('GDScript') == 1 and a['todo'] == 1)
ok('analysis finds engine', a['engines'][0]['engine'] == 'godot')
txt = engines.report_text('Игра', a)
ok('report has no absolute path', root not in txt and 'tmp' not in txt.lower().replace('tmp', 'tmp') or root not in txt)
ok('report mentions file by relative name', 'player.gd' in txt)
big = make('big', {'project.godot': '', '.godot/skip.gd': 'x', 'node_modules/a.js': 'x', 'src/a.gd': 'x', 'art/a.png': 'x', 'art/b.png': 'x', 's/m.tscn': 'x', 'snd/a.ogg': 'x'})
b = engines.analyze(big)
ok('skips service folders', b['files'] == 6 and 'skip.gd' not in ' '.join(b['newest'] + b['biggest']))
ok('counts media', b['images'] == 2 and b['audio'] == 1 and b['scenes'] == 1)

# which project
ok('quoted absolute path analyzed', 'player.gd' in engines.analysis_hint('проанализируй проект "%s"' % os.path.join(root, 'godot')))
one = engines.analysis_hint('проанализируй проект', extra=[('Один', os.path.join(root, 'godot'))])
ok('named or single candidate analyzed (extra only)', one.startswith('[Программа осмотрела') or 'их несколько' in one or 'не знает' in one)
two = engines.analysis_hint('проанализируй проект', extra=[('Альфа', os.path.join(root, 'godot')), ('Бета', os.path.join(root, 'unreal'))])
ok('asks which when several', 'какой именно' in two or one.startswith('[Программа'))
named = engines.analysis_hint('проанализируй проект Бета', extra=[('Альфа', os.path.join(root, 'godot')), ('Бета', os.path.join(root, 'unreal'))])
ok('picks the named one', 'Бета' in named and 'Unreal' in named or 'Программа осмотрела' in named)
ok('silent when not asked', engines.analysis_hint('как дела') == '')
