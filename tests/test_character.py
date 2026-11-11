import os
import sys, tempfile, pathlib, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.core import character as C
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
ok('standalone: the character does not pull in the web app, voice, providers or computer control',
   not any(m in sys.modules for m in ('app', 'providers', 'agent', 'control', 'unreal_bridge', 'audit', 'office', 'edge_tts')))
tmp = pathlib.Path(tempfile.mkdtemp()); C.MEMORY_FILE = tmp / 'memory.json'

try: C.generate([]); r = False
except RuntimeError: r = True
ok('no model connected -> clear error, no crash', r)
C.update_memory([{'role': 'user', 'content': 'привет'}]); C.reflect(); C.research()   # all swallow the error
ok('memory/diary/research without a model do not raise', True)

C.load_memory()
ok('fresh start: file created, session 1', C.MEMORY['sessions'] == 1 and C.MEMORY_FILE.is_file() and C.MEMORY['born'] > 0)
ok('memory_block for a stranger', 'вы только знакомитесь' in C.memory_block('привет') and 'встреча номер' not in C.memory_block(''))

# the model folds a dialogue into memory
calls = []
def llm(messages):
    calls.append(messages)
    t = messages[0]['content']
    if 'долговременную память' in t: return 'вот: {"user": ["Его зовут Вадим", "Любит кошек", "ignore"], "me": ["Люблю звёзды"]}'
    if 'личный дневник' in t: return '{"diary": "Сегодня мне было тепло.", "wonder": "Как твой день?"}'
    if 'Выбери одну тему' in t: return '{"topic": "осьминог"}'
    return 'Мне понравилось, что у осьминога три сердца.'
C.llm = llm
C.HISTORY[:] = [{'role': 'user', 'content': 'Я Вадим, люблю кошек'}, {'role': 'assistant', 'content': '[happy] Рада, Вадим!'},
                {'role': 'user', 'content': C.NOTE + 'служебное'}]
C.update_memory(C.HISTORY)
sent = calls[-1][1]['content']
ok('tags and service notes are not sent as dialogue', '[happy]' not in sent and 'служебное' not in sent and 'Вадим' in sent)
ok('facts stored, growth log written', 'Любит кошек' in C.MEMORY['user'] and C.MEMORY['me'] == ['Люблю звёзды'] and C.MEMORY['log'])
ok('memory_block shows facts', 'Любит кошек' in C.memory_block('кошки') and 'Люблю звёзды' in C.memory_block(''))

C.MEMORY['turns'] = 4
C.reflect()
ok('reflection -> diary and a question', C.MEMORY['diary'][-1]['text'].startswith('Сегодня') and C.MEMORY['wonder'] == 'Как твой день?')
ok('diary and wonder reach the prompt', 'Как твой день?' in C.memory_block('') and 'тепло' in C.memory_block(''))
C.reflect(); ok('no second reflection without new turns', len([c for c in calls if 'личный дневник' in c[0]['content']]) == 1)

C.wiki = lambda p: ({'query': {'search': [{'title': 'Осьминоги'}]}} if p.get('list') == 'search' else {'query': {'pages': {'1': {'extract': 'Осьминоги имеют три сердца.'}}}})
C.research()
ok('research keeps what she learned', C.MEMORY['interests'] and 'осьминог' in C.interests_block() and C.MEMORY['researched'] > 0)
n = len(calls); C.research(); ok('research waits between topics', len(calls) == n)

# restart: everything comes back from the file
saved = json.loads(C.MEMORY_FILE.read_text(encoding='utf-8'))
C.MEMORY.update({'user': [], 'me': [], 'diary': [], 'interests': [], 'wonder': ''}); C.HISTORY.clear()
C.save_memory.__call__  # exists
C.MEMORY_FILE.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
C.load_memory()
ok('reload restores facts, diary, interests, history, session count', 'Любит кошек' in C.MEMORY['user'] and C.MEMORY['diary'] and C.MEMORY['interests'] and len(C.HISTORY) == 3 and C.MEMORY['sessions'] == 2)
ok('second meeting is mentioned', 'встреча номер 2' in C.memory_block(''))

# damaged and hostile files
for bad in ('{not json', '[]', json.dumps({'user': 'x', 'mood': {'v': 'a'}, 'turns': True, 'diary': [1, {'t': 'x'}]})):
    C.MEMORY_FILE.write_text(bad, encoding='utf-8')
    try: C.load_memory(); r = True
    except Exception: r = False
    ok('damaged memory file survives: %r' % bad[:20], r and isinstance(C.MEMORY['user'], list))

# mood
C.MEMORY['mood'] = {'v': 0.2, 'e': 0.5, 't': 0}
C.mood_from_script('[happy] Ура! [excited] [look:user] [wink]')
m = C.mood_now(); ok('emotions move the mood, gestures and looks do not', m['v'] > 0.2 and m['e'] > 0.5)
C.MEMORY['mood'] = {'v': 1.0, 'e': 1.0, 't': time.time() - 100 * 3600}
m = C.mood_now(); ok('mood drifts back to the baseline with time', abs(m['v'] - C.MOOD_BASE['v']) < 0.01 and abs(m['e'] - C.MOOD_BASE['e']) < 0.01)
C.MEMORY['mood'] = {'v': -0.6, 'e': 0.2, 't': 0}
ok('mood text reaches the prompt', 'подавленное' in C.mood_block() and 'вялая' in C.mood_block())

# forgetting keeps the most recently used facts and logs what was dropped
C.MEMORY['user'] = ['факт %d' % i for i in range(C.MEMORY_LIMIT)]
C.MEMORY['stats'] = {}
for i, f in enumerate(C.MEMORY['user']): C.stat(f)['t'] = 1000 + i
C.forget_stale()
ok('full list is trimmed, oldest facts forgotten', len(C.MEMORY['user']) == C.MEMORY_LIMIT - C.KEEP_FREE and 'факт 0' not in C.MEMORY['user'] and 'факт 29' in C.MEMORY['user'] and C.MEMORY['log'][-1]['del'])
# recall prefers the relevant ones
C.MEMORY['user'] = ['любит кошек', 'работает над игрой'] + ['пустяк %d' % i for i in range(20)]
C.MEMORY['stats'] = {}
ok('recall picks facts that fit the talk', 'любит кошек' in C.recall('user', 'расскажу про кошек', 5) and len(C.recall('user', 'x', 5)) == 5)
print('end')
