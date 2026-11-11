"""Game-engine error table (gameerrors.py): known fixed error texts are recognised; ordinary talk is silent."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.dev import gameerrors
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

cases = [("Invalid call. Nonexistent function 'move_and_slide' in base 'Nil'.", 'Godot'), ("Node not found: \"Player/Sprite\" (relative to \"/root/Main\").", 'Godot'),
         ("Parser Error: Identifier \"speed\" not declared in the current scope.", 'Godot'), ("res://art/hero.png not found", 'Godot'),
         ("NullReferenceException: Object reference not set to an instance of an object", 'Unity'), ("Assets/Player.cs(12,5): error CS0246: The type or namespace name 'Foo' could not be found", 'Unity'),
         ("error CS0103: The name 'speed' does not exist in the current context", 'Unity'), ("MissingReferenceException: The object of type 'Enemy' has been destroyed", 'Unity'),
         ("MyGame.obj : error LNK2019: unresolved external symbol", 'Unreal'), ("fatal error C1083: Cannot open include file: 'Foo.h'", 'Unreal'),
         ("Unhandled Exception: EXCEPTION_ACCESS_VIOLATION reading address 0x0", 'Unreal'), ("Blueprint Runtime Error: Accessed None trying to read property Target", 'Unreal'),
         ("Variable obj_player.speed(100002, -2147483648) not set before reading it.", 'GameMaker'), ("error[E0499]: cannot borrow `*world` as mutable more than once", 'Bevy'),
         ("Uncaught TypeError: Cannot read properties of undefined (reading 'add')", 'Phaser'), ("Access to image at 'file:///x.png' blocked by CORS policy", 'Web'),
         ("Error: main.lua:12: attempt to index a nil value (global 'player')", 'LÖVE'), ("pygame.error: video system not initialized", 'Pygame'),
         ("ModuleNotFoundError: No module named 'pygame'", 'Python'), ("IndentationError: unexpected indent in script.rpy", "Ren'Py"),
         ("Shader error in 'Custom/Wave': undeclared identifier 'foo' at line 40", 'Shader')]
for text, engine in cases:
    got = gameerrors.match(text)
    ok('recognised %s: %s' % (engine, text[:40]), any(g[0] == engine for g in got))
for text in ['как дела?', 'сделай платформер в Godot', 'мой персонаж не двигается, помоги', 'what is a null pointer', '', 'Ошибка', 'я получил ошибку, не знаю что делать']:
    ok('silent: ' + text, gameerrors.hint(text) == '')
h = gameerrors.hint("Invalid call. Nonexistent function 'x' in base 'Nil'. NullReferenceException")
ok('hint is a note, mentions both engines, says typical not diagnosis', h.startswith('[') and 'Godot' in h and 'Unity' in h and 'не диагноз' in h)
ok('at most three notes', len(gameerrors.match(' '.join(c[0] for c in cases))) <= 3)
ok('all patterns compile and every row has four fields', all(len(r) == 4 for r in gameerrors.ERRORS) and all(re.compile(r[1]) for r in gameerrors.ERRORS))
ok('table large enough', len(gameerrors.ERRORS) >= 30)
