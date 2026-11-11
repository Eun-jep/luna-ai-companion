"""When she asks for more engine operations than fit in one reply, the extra ones are not queued and he is told (no silent drop); i18n has the message in all four languages."""
import json
import os
import pathlib
import re
import sys
import tempfile
os.environ['LUNA_TEST'] = '1'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.core import character
character.MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'
import app
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

i18n = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web', 'i18n.js'), encoding='utf-8').read()
ok('capped message in four languages for godot and unity', len(re.findall(r"'godot\.err\.capped'", i18n)) == 4 and len(re.findall(r"'unity\.err\.capped'", i18n)) == 4)

reply = {'text': ''}


class R:
    def __init__(s):
        s.l = [('data: ' + json.dumps({'choices': [{'delta': {'content': reply['text']}}]}) + '\n').encode(), b'data: [DONE]\n']

    def __iter__(s): return iter(s.l)
    def read(s): return json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()
    def __enter__(s): return s
    def __exit__(s, *a): pass
    def close(s): pass


app.open_api = lambda messages, **kw: R()
app.providers.ready = lambda: True



def events(text, say):
    reply['text'] = say
    out = []
    for ev in app.chat_turn({'message': text, 'lang': 'ru', 'agent': True, 'work': True}):
        if isinstance(ev, dict):
            out.append(ev)
    return out


five_gd = 'Делаю. [gd:scene Main 2d] [gd:node Main Node2D A] [gd:node Main Node2D B] [gd:node Main Node2D C] [gd:node Main Node2D D]'
ev = events('построй сцену в Godot', five_gd)
ok('godot: four-plus operations -> capped notice', any(e.get('godotfail') == 'capped' for e in ev))
ev = events('построй сцену в Godot', 'Делаю. [gd:scene Main 2d] [gd:node Main Node2D A]')
ok('godot: two operations -> no capped notice', not any(e.get('godotfail') == 'capped' for e in ev))
five_un = 'Делаю. [unity:scene Main 3d] [unity:object Main cube A] [unity:object Main cube B] [unity:object Main cube C]'
ev = events('построй сцену в Unity', five_un)
ok('unity: four operations -> capped notice', any(e.get('unityfail') == 'capped' for e in ev))
