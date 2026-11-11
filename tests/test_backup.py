"""A rolling backup of her memory: a week of copies, and a damaged or lost memory.json comes back from the newest good copy."""
import os
import sys, json, tempfile, pathlib, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from luna.core import character as C
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
tmp = pathlib.Path(tempfile.mkdtemp())
C.MEMORY_FILE = tmp / 'memory.json'   # never her real memory

ok('no file, no copy', C.backup_memory() is False and C.backups() == [])
C.load_memory()   # a fresh start writes a file
C.MEMORY['user'] = ['любит дождь']; C.save_memory()
ok('a healthy file is copied', C.backup_memory() is True and len(C.backups()) == 1)
ok('the copy reads back the same', json.loads(C.backups()[0].read_text(encoding='utf-8'))['user'] == ['любит дождь'])
ok('not again within twelve hours', C.backup_memory() is False and len(C.backups()) == 1)

# age the copies, make more: only seven stay, the newest ones
folder = C.MEMORY_FILE.parent / 'memory-backups'
for i in range(10):
    p = folder / ('memory-2020010%d-000000.json' % i if i < 10 else 'x')
    p.write_text(C.MEMORY_FILE.read_text(encoding='utf-8'), encoding='utf-8')
    os.utime(p, (time.time() - 90000 - i, time.time() - 90000 - i))
for p in C.backups()[:1]:
    os.utime(p, (time.time() - 90000, time.time() - 90000))   # the very first one is old too
ok('after twelve hours a new copy is made', C.backup_memory() is True)
ok('only seven copies are kept', len(C.backups()) == C.BACKUP_KEEP)
ok('the newest is kept, the oldest went', C.backups()[0].name > 'memory-2025' and not (folder / 'memory-20200100-000000.json').exists())

# a damaged file is not copied over good copies, and it is restored
good = C.MEMORY_FILE.read_text(encoding='utf-8')
C.MEMORY_FILE.write_text('{ this is broken', encoding='utf-8')
before = len(C.backups())
ok('a damaged file is never backed up', C.backup_memory() is False and len(C.backups()) == before)
ok('a damaged file is restored from a copy', C.restore_memory() is True and json.loads(C.MEMORY_FILE.read_text(encoding='utf-8'))['user'] == ['любит дождь'])
ok('the damaged file is kept aside', any(p.read_text(encoding='utf-8') == '{ this is broken' for p in tmp.glob('memory-damaged-*.json')))
C.MEMORY_FILE.unlink()
ok('a lost file is restored too', C.restore_memory() is True and C.MEMORY_FILE.is_file())

# through the real loader: she comes back with her memory
C.MEMORY_FILE.write_text('garbage', encoding='utf-8')
C.MEMORY['user'] = []
C.load_memory()
ok('loading a damaged file brings back what she knew', C.MEMORY['user'] == ['любит дождь'])

# no copies, damaged file: a fresh start, nothing crashes
other = pathlib.Path(tempfile.mkdtemp())
C.MEMORY_FILE = other / 'memory.json'
C.MEMORY_FILE.write_text('garbage', encoding='utf-8')
ok('with no copy a damaged file is a fresh start, not a crash', C.restore_memory() is False)
C.MEMORY['user'] = []; C.load_memory()
ok('and it runs', C.MEMORY['user'] == [] and C.MEMORY_FILE.is_file())

# a file that is valid JSON but not a memory is not backed up
C.MEMORY_FILE.write_text('[1, 2]', encoding='utf-8')
ok('something that is not a memory is not backed up', C.backup_memory() is False)
ok('the app loads the real thing from the project folder, backups next to memory.json', C.backups.__doc__ and 'memory-backups' in open(os.path.join(ROOT, 'luna', 'core', 'character.py'), encoding='utf-8').read())

# forgetting takes the copies with it
C.MEMORY_FILE = tmp / 'memory.json'
C.MEMORY_FILE.write_text(good, encoding='utf-8')
(tmp / 'memory-damaged-20200101-000000.json').write_text('x', encoding='utf-8')
ok('there are copies before forgetting', len(C.backups()) > 0)
C.erase_backups()
ok('forgetting erases every copy and the damaged files', C.backups() == [] and not (tmp / 'memory-backups').exists() and not list(tmp.glob('memory-damaged-*.json')))
ok('and the memory file itself is not touched by that', C.MEMORY_FILE.read_text(encoding='utf-8') == good)
ok('the forget route calls it', 'character.erase_backups()' in ''.join(open(os.path.join(ROOT, *f), encoding='utf-8').read() for f in (('app.py',), ('luna', 'server', 'chat.py'), ('luna', 'server', 'hands.py'))))
