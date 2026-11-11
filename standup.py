"""The daily stand-up she keeps with him in work mode: what he did yesterday, what he plans today, what blocks him.
Notes stay in standup.json next to the program; she writes one only after he has told her, and says so."""
import paths
import json
import os
import re
import time

FILE = str(paths.data_file('standup.json'))
KEEP, ITEMS, ITEM_LEN = 60, 8, 200
FIELDS = (('yesterday', 'вчера'), ('today', 'сегодня'), ('blockers', 'блокеры'))


def load():
    try:
        with open(FILE, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and isinstance(e.get('date'), str)] if isinstance(data, list) else []


def _write(entries):
    tmp = FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(entries[-KEEP:], f, ensure_ascii=False, indent=1)
    os.replace(tmp, FILE)


def clear():
    try:
        os.remove(FILE)
    except OSError:
        pass


def _items(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [' '.join(v.split())[:ITEM_LEN] for v in value if isinstance(v, str) and v.strip()][:ITEMS]


def save(source, today=None):
    """Keeps one stand-up from her block (JSON text). One note per day: a second one replaces the first.
    Returns the saved entry, or None when there was nothing usable."""
    try:
        data = json.loads(source)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    entry = {key: _items(data.get(key)) for key, _ in FIELDS}
    if not any(entry.values()):
        return None
    entry['date'] = today or time.strftime('%Y-%m-%d', time.localtime())
    entries = [e for e in load() if e['date'] != entry['date']] + [entry]
    entries.sort(key=lambda e: e['date'])
    _write(entries)
    return entry


def _line(entry):
    parts = ['%s: %s' % (label, '; '.join(entry.get(key) or [])) for key, label in FIELDS if entry.get(key)]
    return '%s — %s' % (entry['date'], ' | '.join(parts))


def block(today=None):
    """The stand-up section of the prompt in work mode: how to run it, and what he said before."""
    today = today or time.strftime('%Y-%m-%d', time.localtime())
    entries = load()
    done_today = any(e['date'] == today for e in entries)
    text = (
        '\n\nСтендап: если он просит стендап, итоги дня или недели, или ты предлагаешь это утром и он согласен, веди его как живой коллега, '
        'не анкетой: по одному вопросу за раз (что сделал вчера, что планирует сегодня, что мешает), откликайся на ответы по-человечески '
        'и помогай, если он застрял. Когда он всё рассказал, коротко подытожь вслух и поставь блок кода с языком lunastandup: внутри только '
        'валидный JSON {"yesterday":["..."],"today":["..."],"blockers":["..."]}, каждый пункт одной короткой строкой его словами, пустой список, '
        'если сказать нечего. Блок вслух не читается; приложение запишет заметку, после этого скажи «записала». Без его рассказа ничего не '
        'записывай и не выдумывай. Если просит текст для команды, составь его по заметкам обычным сообщением (вчера, сегодня, блокеры). ')
    text += ('Сегодняшний стендап уже записан: не предлагай его снова, если он сам не просит обновить.' if done_today else
             'Сегодняшнего стендапа ещё нет: в начале рабочего разговора можно один раз и мимоходом предложить его.')
    if entries:
        last = entries[-1]
        if last['date'] != today and (last.get('today') or last.get('blockers')):
            text += ' В прошлый раз (%s) он планировал: %s.%s Спроси, как вышло, но не как проверяющий.' % (
                last['date'], '; '.join(last.get('today') or ['—']),
                (' Мешало: ' + '; '.join(last['blockers']) + '.') if last.get('blockers') else '')
        text += '\nЗаметки последних стендапов (для вопросов «что я делал на неделе», «что у меня висит»):\n' + '\n'.join(
            _line(e) for e in entries[-5:])
    return text[:3000]
