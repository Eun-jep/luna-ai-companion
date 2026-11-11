"""When he says she was wrong, she keeps where, and the same subject later comes with his correction (character.learn_lesson / lessons_hint)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tempfile, pathlib
from luna.core import character
character.MEMORY_FILE = pathlib.Path(tempfile.mkdtemp()) / 'memory.json'   # never her real memory
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

character.MEMORY['lessons'] = []
ok('a lesson is kept', character.learn_lesson('какая столица Австралии?', 'ты ошиблась, это Канберра, не Сидней'))
ok('too short a correction is not kept', not character.learn_lesson('какая столица Австралии?', 'нет'))
ok('same subject: the correction comes next to the message', 'Канберра' in character.lessons_hint('напомни столица Австралии какая'))
ok('another subject: nothing', character.lessons_hint('расскажи про погоду в Сеуле') == '')
ok('one common word is not enough', character.lessons_hint('Австралии привет') == '')
character.learn_lesson('какая столица Австралии?', "you're wrong, it is Canberra")
ok('same question replaces the old lesson', len(character.MEMORY['lessons']) == 1 and 'Canberra' in character.MEMORY['lessons'][0]['fix'])
for i in range(30):
    character.learn_lesson('вопрос номер %d про слонов' % i, 'неправильно, ответ номер %d другой' % i)
ok('the shelf is limited', len(character.MEMORY['lessons']) == character.LESSON_LIMIT)
character.save_memory(); character.MEMORY['lessons'] = []; character.load_memory()
ok('lessons survive a restart', len(character.MEMORY['lessons']) == character.LESSON_LIMIT)
for q, fix in [('질문 하나', '그건 틀렸어, 다시 봐'), ('質問です', 'それは違うよ、よく見て')]:
    ok('lesson from ' + fix[:4], character.learn_lesson(q, fix) is not None)
