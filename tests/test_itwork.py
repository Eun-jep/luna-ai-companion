"""What she can be as a colleague in an IT team: topics for review, debugging, documents and tools, and their guides (devtools.py)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.dev import devtools
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

t = devtools.topics
ok('review', 'review' in t('посмотри мой pull request') and 'review' in t('напиши сообщение коммита'))
ok('debug', 'debug' in t('программа падает с traceback') and 'debug' in t('app вылетает при старте'))
ok('docs', 'docs' in t('помоги с README') and 'docs' in t('нужен баг-репорт') and 'docs' in t('итоги встречи составь'))
ok('ops', 'ops' in t('как откатить git коммит') and 'ops' in t('нужен sql запрос') and 'ops' in t('регулярка regex'))
ok('code always comes along', all('code' in t(x) for x in ('мой pull request', 'нужен sql запрос')))
ok('small talk is not dev talk', t('привет как дела') == [] and t('у меня не работает чайник') == [])
ok('every topic has a guide', all(k in devtools.GUIDES for k in devtools.TOPIC_RES))
block = devtools.dev_block('помоги с pull request и git', [])
ok('the block carries both guides', 'ревьюер' in block and 'git (ветки' in block)
ok('guides warn about irreversible git and secrets', 'push --force' in devtools.GUIDES['ops'] and 'Секреты' in devtools.GUIDES['ops'])
