"""The family side of her character: people in his life, how close they are, and the persona text (character.py). Fake model."""
import os
import sys, tempfile, pathlib, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import character as C
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

tmp = pathlib.Path(tempfile.mkdtemp()); C.MEMORY_FILE = tmp / 'memory.json'
C.load_memory()
ok('fresh memory: no people, no block', C.MEMORY['people'] == [] and C.people_block() == '')

answer = {'user': ['Его зовут Вадим'], 'me': [], 'people': [
    {'name': 'Мина', 'who': 'младшая сестра, учится в школе'}, {'name': 'мина', 'who': 'дубль'},
    {'name': '', 'who': 'без имени'}, 'строка', {'name': 'Тэ', 'who': 'друг по команде'}]}
calls = []
C.llm = lambda m: (calls.append(m), json.dumps(answer))[1]
C.update_memory([{'role': 'user', 'content': 'у меня сестра Мина, и друг Тэ'}])
ok('people are kept; duplicates, empty and junk are skipped', [p['name'] for p in C.MEMORY['people']] == ['Мина', 'Тэ'])
ok('people go to the prompt', 'Мина — младшая сестра' in C.memory_block('') and 'Люди в жизни' in C.memory_block(''))
ok('current people are shown to the model for the next update', 'Мина' in calls[-1][1]['content'])
C.save_memory(); C.MEMORY['people'] = []; C.load_memory()
ok('people survive a restart', len(C.MEMORY['people']) == 2)
answer['people'] = 'не список'
C.update_memory([{'role': 'user', 'content': 'привет'}])
ok('a malformed answer does not erase them', len(C.MEMORY['people']) == 2)

C.MEMORY['turns'], C.MEMORY['sessions'] = 0, 1
ok('strangers: careful', 'знакомитесь' in C.closeness_block())
C.MEMORY['turns'], C.MEMORY['sessions'] = 100, 5
ok('friends', 'подружились' in C.closeness_block())
C.MEMORY['turns'] = 400
ok('family', 'как семья' in C.closeness_block())
ok('closeness is part of the persona block', C.closeness_block() in C.persona_block())
ok('persona says family first, abilities second', 'член его семьи' in C.PERSONA and 'дополнения' in C.PERSONA)
