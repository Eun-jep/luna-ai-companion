"""How the creator writes (character.note_style / style_block): a hint for her tone, built from numbers only."""
import os
import sys, tempfile, pathlib, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.core import character
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
character.MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'

character.MEMORY['style'] = {}
for _ in range(3): character.note_style('привет')
ok('too little to go on: no hint', character.style_block() == '')
for t in ['ща че делаешь', 'ахах ну ты даёшь))', 'блин не работает'] * 3: character.note_style(t)
b = character.style_block()
ok('short lowercase talk: short and simple', 'коротко' in b and 'с маленькой буквы' in b)
ok('rough words: no sermon, and no copying', 'мораль' in b and 'не копируй мат' in b)
ok('only numbers are kept, never his words', all(isinstance(v, (int, float)) for v in character.MEMORY['style'].values()) and 'ща' not in json.dumps(character.MEMORY['style']))
character.MEMORY['style'] = {}
for _ in range(10): character.note_style('오늘 뭐 해? 같이 게임 할까요')
ok('Korean writer: she answers in Korean', 'по-корейски' in character.style_block())
character.MEMORY['style'] = {}
for _ in range(10): character.note_style('Расскажи подробно, как устроена система памяти в этом проекте, и почему вы выбрали именно такой подход к хранению данных в файле. ' * 2)
ok('long writer: detailed answers are fine', 'подробно' in character.style_block())
n = character.MEMORY['style']['n']
character.note_style(character.NOTE + 'служебная заметка')
ok('her own service notes are not his style', character.MEMORY['style']['n'] == n)
character.save_memory(); character.MEMORY['style'] = {}; character.load_memory()
ok('the style survives a restart', character.MEMORY['style'].get('n') == n)

# ---- a shift from his usual manner ----
character.MEMORY['style'] = {}; character.RECENT.clear()
LONG = 'Расскажи подробно, как устроена система и почему она так работает, мне правда интересно разобраться в деталях.'
for _ in range(25): character.note_style(LONG + ' ахах :)')
ok('his usual manner alone is no shift', character.shift_block() == '')
for t in ('ага', 'ну', 'да'): character.note_style(t)
b = character.shift_block()
ok('suddenly curt: she is told, without a diagnosis', 'заметно короче' in b and 'ни одного' in b and 'Не ставь диагноз' in b and 'ты как?' in b)
ok('the shift rides in the style block', 'Заметный сдвиг' in character.style_block())
for _ in range(3): character.note_style(LONG + ' ахах :)')
ok('back to normal: no shift', character.shift_block() == '' and 'Заметный сдвиг' not in character.style_block())
character.MEMORY['style'] = {}; character.RECENT.clear()
for _ in range(25): character.note_style('ща че делаешь')
for _ in range(3): character.note_style('Слушай, ' + 'у меня накопилось очень много мыслей про всё это, ' * 6)
ok('unusually long after short ones is noticed', 'необычно длинные' in character.shift_block())
character.MEMORY['style'] = {}; character.RECENT.clear()
for _ in range(5): character.note_style(LONG)
for t in ('ага', 'ну', 'да'): character.note_style(t)
ok('too early to judge: nothing', character.shift_block() == '')
