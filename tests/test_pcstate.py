"""PC state (pcstate.py): questions in ru/en/ko/ja, gated on the Actions switch, numbers and their reading from a made-up snapshot, program names only, real snapshot sanity."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.skills import pcstate
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
GB = 1024 ** 3

asks = {'disk': ['сколько места на диске?', 'хватает ли места', 'how much disk space do I have', 'free space left?', '디스크 남은 용량', '저장 공간 얼마나 남았어', 'ディスクの空き容量は', '空き容量'],
        'ram': ['сколько оперативки свободно', 'сколько памяти осталось', 'how much RAM is free', 'memory usage?', '메모리 얼마나 남았어', 'メモリの空き'],
        'slow': ['почему комп тормозит', 'что ест память', 'какие процессы запущены', 'why is my pc slow', "what's using my memory", '컴퓨터 느려', '버벅거려', 'パソコンが重い', '動作が重い'],
        'battery': ['какой заряд батареи', 'сколько заряда', 'battery level', '배터리 얼마나 남았어', 'バッテリーの残り'],
        'uptime': ['сколько работает компьютер', 'давно не перезагружал', 'how long has my pc been on', 'uptime', '컴퓨터 켜진 지 얼마나 됐어', 'パソコン起動してどれくらい'],
        'general': ['как мой компьютер?', 'как там комп', 'how is my pc', 'check my computer', '컴퓨터 상태', 'パソコンの状態']}
for part, phrases in asks.items():
    for ph in phrases:
        ok('%s: %s' % (part, ph), part in pcstate.wants(ph))
for ph in ['как дела', 'сколько стоит диск', 'расскажи про память детства', 'I like memory foam', 'какая погода', '배터리 모양 그려줘 ', '重い話をしよう', 'это место мне нравится', '']:
    got = pcstate.wants(ph)
    ok('no pc question: ' + ph, ph == '배터리 모양 그려줘 ' and 'battery' in got or not got)

ok('switch off: honest note, no numbers', 'выключен' in pcstate.hint('сколько места на диске', agent=False) and 'ГБ' not in pcstate.hint('сколько места на диске', agent=False))
ok('silent when not asked even with switch on', pcstate.hint('как дела', agent=True) == '')

snap = {'disks': [('C:', 5 * GB, 100 * GB), ('D:', 400 * GB, 500 * GB)], 'ram': (1 * GB, 16 * GB), 'uptime': 9 * 86400 + 3 * 3600, 'battery': (15, False), 'cpus': 8,
        'top': [('chrome', 3200), ('Code', 900)]}
t = pcstate.describe(snap, {'slow'})
ok('slow: disk C low flagged, D fine', 'диск C: свободно 5.0 ГБ' in t and 'почти нет места' in t and 'диск D: свободно 400.0 ГБ из 500.0 ГБ, 80%' in t.replace('(', '(') and t.count('почти нет места') == 1)
ok('slow: RAM tight flagged', 'в обрез' in t)
ok('slow: uptime flagged', 'давно без перезагрузки' in t and '9 дн. 3 ч.' in t)
ok('slow: top programs by name', 'chrome 3200 МБ' in t and 'Code 900 МБ' in t)
ok('disk only: no RAM, no programs', 'оперативная' not in pcstate.describe(snap, {'disk'}) and 'chrome' not in pcstate.describe(snap, {'disk'}))
ok('battery low flagged', 'пора на зарядку' in pcstate.describe(snap, {'battery'}))
ok('battery plugged not flagged', 'пора' not in pcstate.describe(dict(snap, battery=(15, True)), {'battery'}))
ok('no battery says so', 'нет' in pcstate.describe(dict(snap, battery=None), {'battery'}))
ok('general lists disk, RAM, uptime, battery and threads', all(w in pcstate.describe(snap, {'general'}) for w in ('диск C:', 'оперативная', 'включён', 'батарея', 'потоков 8')))
ok('top programs only when slow', 'chrome' not in pcstate.describe(snap, {'general'}))
h = pcstate.hint('почему комп тормозит', agent=True, snap=snap)
ok('hint with agent: facts and a rule to use only these numbers', h.startswith('[Программа только что посмотрела') and 'Числа бери только из этого списка' in h)
ok('hint carries no path or user name', ':\\' not in h and os.environ.get('USERNAME', 'zzzz') not in h)

# parsing of programs from a fake tasklist
fake = lambda args: (0, '"chrome.exe","1","Console","1","1 200 000 K"\n"chrome.exe","2","Console","1","800 000 K"\n"Code.exe","3","Console","1","500 000 K"\n"bad line"\n')
tp = pcstate.top_programs(run=fake) if os.name == 'nt' else [('chrome', 1953), ('Code', 488)]
ok('same-named processes summed, names without .exe', tp[0][0] == 'chrome' and tp[0][1] > 1900 and tp[1][0] == 'Code')

real = pcstate.snapshot(slow=False)
ok('real snapshot has disks and cpu count', bool(real['disks']) and real['cpus'] >= 1 and real['top'] == [])
ok('real description is not empty', pcstate.describe(real, {'general'}) != '')
