"""How is his computer doing: "почему комп тормозит", "сколько места на диске", "сколько оперативки свободно", "заряд батареи", "сколько работает компьютер",
"why is my pc slow", "how much disk space", "컴퓨터 느려", "ディスクの空き" (ru/en/ko/ja). The program reads a fixed, read-only snapshot (free disk per drive, RAM, uptime, battery, CPU count and,
only when the question is about slowness or memory, the five biggest programs by name and memory) and hands her the numbers with the usual reading of them. Nothing is changed or stopped.
Only the Actions switch lets it run (it is his computer's data going to the model), and only on his own question. No paths, no user names, no window titles: program names only."""
import ctypes
import os
import re
import time

import envdiag

_DISK = re.compile(r'(?i)(?:сколько|много ли|хватает ли).{0,25}(?:места|памяти на диск)|свободн\w* мест\w*|место на диске|на диске.{0,15}(?:место|свободно|осталось)|(?:how much|how many).{0,25}(?:disk|storage|space)|'
                   r'(?:free|left|available).{0,12}(?:disk|storage|space)|disk space|storage left|디스크.{0,8}(?:남|용량|공간)|저장 ?공간|용량이 (?:얼마|부족)|ディスク.{0,6}(?:空き|容量)|ストレージ.{0,6}(?:空き|容量)|空き容量')
_RAM = re.compile(r'(?i)оператив\w*|\bозу\b|(?:сколько|много ли).{0,20}памят|свободн\w* памят|\bram\b|how much (?:ram|memory)|memory (?:left|free|usage)|메모리.{0,8}(?:남|사용|얼마|부족)|램이|メモリ.{0,6}(?:空き|使用|足り)')
_SLOW = re.compile(r'(?i)тормоз|лагает|зависает|медленно работает|что (?:грузит|ест|жрёт|жрет|занимает)|(?:грузит|ест) (?:процессор|память|комп)|какие процессы|что запущено|'
                   r'(?:pc|computer|laptop|it).{0,12}(?:slow|lag|laggy|freez)|slow(?:ing)? down|what.?s (?:using|eating|hogging)|which (?:processes|programs)|컴퓨터.{0,6}(?:느려|렉|버벅)|버벅|렉이|프로세스|'
                   r'(?:パソコン|PC).{0,6}(?:遅い|重い|固まる|フリーズ)|動作が重い|重くなっ|プロセス')
_BATTERY = re.compile(r'(?i)батаре\w+|заряд\w*|аккумулятор|разряжен|battery|charge level|how much charge|배터리|충전|バッテリー|充電')
_UPTIME = re.compile(r'(?i)сколько (?:уже )?(?:работает|включён|включен) (?:комп|компьютер|пк|ноут)|аптайм|давно (?:не )?перезагружал|how long.{0,15}(?:been on|running|up)|uptime|last (?:restart|reboot)|'
                     r'(?:컴퓨터|PC).{0,8}(?:켜진|켜져|가동)|(?:パソコン|PC).{0,8}(?:起動して|稼働|つけっぱなし)|稼働時間')
_GENERAL = re.compile(r'(?i)как (?:там )?(?:мой |наш )?(?:комп|компьютер|пк|ноут|ноутбук)\b|что (?:с|у) (?:моим |нашим )?(?:компом|компьютером|пк|ноутом)|как (?:себя )?чувствует себя (?:комп|компьютер)|'
                      r'(?:check|how is|how.?s) (?:my )?(?:pc|computer|laptop|system)|system (?:status|info)|컴퓨터 (?:상태|어때)|내 컴퓨터|(?:パソコン|PC)の(?:状態|調子)|(?:パソコン|PC)(?:は|って)(?:どう|大丈夫)')

OFF = ('[Он спрашивает про состояние своего компьютера, но переключатель «Действия» выключен: программа не смотрит диск, память и процессы, пока он его не включит. '
       'Скажи об этом честно и коротко (включить можно в настройках) и не называй никаких чисел из головы. Общий совет по такой теме дать можно.]')


def wants(text):
    """Which parts he asks about: a set of 'disk', 'ram', 'slow', 'battery', 'uptime', 'general'; empty when he asks nothing about the computer's state."""
    text = str(text or '')[:200]
    found = {k for k, rx in (('disk', _DISK), ('ram', _RAM), ('slow', _SLOW), ('battery', _BATTERY), ('uptime', _UPTIME), ('general', _GENERAL)) if rx.search(text)}
    if 'battery' in found and not re.search(r'(?i)батаре|аккумулятор|заряд|battery|배터리|충전|バッテリー|充電', text):
        found.discard('battery')
    if 'general' in found and len(found) > 1:
        found.discard('general')
    return found


def _uptime():
    if os.name != 'nt':
        return None
    try:
        return ctypes.windll.kernel32.GetTickCount64() / 1000.0
    except (OSError, AttributeError):
        return None


def _battery():
    """(percent, plugged) or None: desktops without a battery answer None."""
    if os.name != 'nt':
        return None

    class Power(ctypes.Structure):
        _fields_ = [('ac', ctypes.c_ubyte), ('flag', ctypes.c_ubyte), ('pct', ctypes.c_ubyte), ('r', ctypes.c_ubyte), ('life', ctypes.c_ulong), ('full', ctypes.c_ulong)]
    p = Power()
    try:
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(p)) and p.pct != 255 and p.flag != 128:
            return p.pct, p.ac == 1
    except (OSError, AttributeError):
        pass
    return None


def _mem_kb(cell):
    digits = re.sub(r'\D', '', cell)
    return int(digits) if digits else 0


def top_programs(limit=5, run=None):
    """[(program name, total MB)] by memory, same-named processes summed; names only."""
    if os.name != 'nt':
        return []
    code, out = (run or envdiag._sh)(['tasklist', '/fo', 'csv', '/nh'])
    if code != 0:
        return []
    totals = {}
    for line in out.splitlines():
        cells = re.findall(r'"([^"]*)"', line)
        if len(cells) >= 5:
            name = re.sub(r'(?i)\.exe$', '', cells[0])[:40]
            totals[name] = totals.get(name, 0) + _mem_kb(cells[4])
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    return [(n, kb // 1024) for n, kb in ranked[:limit] if kb > 0]


def snapshot(slow=False, run=None):
    return {'disks': envdiag.disks(), 'ram': envdiag.memory(), 'uptime': _uptime(), 'battery': _battery(), 'cpus': os.cpu_count() or 0,
            'top': top_programs(run=run) if slow else []}


def _gb(n):
    return '%.1f ГБ' % (n / 1024 ** 3)


def describe(snap, parts):
    """Plain facts with the usual reading, as one string. Pure: the tests feed it a made-up snapshot."""
    out = []
    want = set(parts) or {'general'}
    everything = 'general' in want
    if everything or 'disk' in want or 'slow' in want:
        for letter, free, total in snap.get('disks', []):
            pct = free * 100 // total if total else 0
            note = ' (почти нет места: Windows и программы начнут тормозить и ругаться)' if pct < 8 or free < 8 * 1024 ** 3 else ' (маловато)' if pct < 15 else ''
            out.append('диск %s свободно %s из %s, %d%%%s' % (letter, _gb(free), _gb(total), pct, note))
    ram = snap.get('ram')
    if ram and (everything or 'ram' in want or 'slow' in want):
        free, total = ram
        pct = free * 100 // total if total else 0
        note = ' (памяти в обрез: система уходит в подкачку, отсюда тормоза)' if pct < 12 else ' (немного)' if pct < 25 else ''
        out.append('оперативная память свободно %s из %s, %d%%%s' % (_gb(free), _gb(total), pct, note))
    up = snap.get('uptime')
    if up is not None and (everything or 'uptime' in want or 'slow' in want):
        days, hours = int(up // 86400), int(up % 86400 // 3600)
        note = ' (давно без перезагрузки: перезагрузка часто лечит тормоза)' if days >= 7 else ''
        out.append('компьютер включён %s%s' % ('%d дн. %d ч.' % (days, hours) if days else '%d ч.' % hours if hours else 'меньше часа', note))
    bat = snap.get('battery')
    if (everything or 'battery' in want) and bat:
        pct, plugged = bat
        note = ' (мало, пора на зарядку)' if pct <= 20 and not plugged else ''
        out.append('батарея %d%%, %s%s' % (pct, 'от сети' if plugged else 'на батарее', note))
    elif 'battery' in want and not bat:
        out.append('батареи нет или программа её не видит (скорее всего это настольный компьютер)')
    if everything and snap.get('cpus'):
        out.append('процессорных потоков %d' % snap['cpus'])
    top = snap.get('top') or []
    if top and 'slow' in want:
        out.append('больше всего памяти занимают: ' + ', '.join('%s %d МБ' % t for t in top))
    return '; '.join(out)


def hint(text, agent=False, snap=None):
    """The note for her with the real numbers, the honest switch-off note, or '' when he asked nothing about the computer."""
    parts = wants(text)
    if not parts:
        return ''
    if not agent:
        return OFF
    snap = snap or snapshot('slow' in parts)
    facts = describe(snap, parts)
    if not facts:
        return ('[Он спрашивает про состояние компьютера, но программа не смогла ничего прочитать (возможно, система не Windows). Скажи это честно и не называй чисел.]')
    return ('[Программа только что посмотрела его компьютер (только чтение, ничего не менялось). Факты: %s. Перескажи по-своему и коротко, отметь только то, что действительно плохо, '
            'и предложи один простой шаг (закрыть тяжёлую программу, освободить место, перезагрузить). Числа бери только из этого списка, процессы не завершай сама.]' % facts)
