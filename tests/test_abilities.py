"""'What can you do' (abilities.py): ru/en/ko/ja, the list follows the Actions and Work switches, silent on ordinary talk."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import abilities
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

for ph in ['что ты умеешь?', 'а что ты ещё умеешь', 'какие у тебя навыки', 'чем ты можешь помочь', 'what can you do?', 'what are your skills', 'how can you help me',
           '뭘 할 수 있어?', '뭐 할 수 있어', '어떤 걸 도와줄 수 있어', '何ができるの？', 'どんなことができる?', 'できること教えて']:
    ok('asked: ' + ph, abilities.asked(ph) and abilities.hint(ph).startswith('[Он спрашивает'))
for ph in ['как дела', 'что ты думаешь о погоде', 'I can do it', 'what do you want to eat', '뭐 먹을래', '何してるの', 'что умеет Godot', 'ты умеешь готовить борщ в игре?']:
    ok('not asked: ' + ph, abilities.hint(ph) == '')

off = abilities.hint('что ты умеешь', agent=False, work=False)
ok('switches off: says both are off and hides hands', '«Действия» выключены' in off and 'рабочий режим выключен' in off and 'руками в Unreal' not in off.split('Сейчас выключено')[0])
act = abilities.hint('что ты умеешь', agent=True, work=False)
ok('agent only: actions listed, work off', 'открыть программу или сайт' in act.split('Сейчас выключено')[0] and 'рабочий режим выключен' in act)
full = abilities.hint('что ты умеешь', agent=True, work=True)
ok('both on: hands listed, nothing off', 'руками в Unreal' in full.split('Сейчас выключено')[0] and 'Сейчас выключено: ничего' in full)
ok('work without agent is still off (work needs actions)', 'рабочий режим выключен' in abilities.hint('what can you do', agent=False, work=True))
ok('limits always honest', all('не обходит капчи' in h and 'Unreal, Unity и Godot' in h for h in (off, act, full)))
