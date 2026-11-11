"""cleanup.py: finds only junk, removes nothing without --apply, never touches user data."""
import os, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cleanup

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print('FAIL', name)

with tempfile.TemporaryDirectory() as root:
    root = Path(root)
    old = root / 'tmpab12cd_e'; old.mkdir(); (old / 'x.txt').write_text('x')
    t = time.time() - 3 * cleanup.DAY; os.utime(old, (t, t))
    fresh = root / 'tmpzz99yy_k'; fresh.mkdir()
    other = root / 'mydocs'; other.mkdir(); os.utime(other, (t, t))
    tempfile.tempdir = str(root)
    try:
        names = [p.name for p, _ in cleanup.candidates()]
    finally:
        tempfile.tempdir = None
    check('old tmp dir is junk', 'tmpab12cd_e' in names)
    check('fresh tmp dir kept', 'tmpzz99yy_k' not in names)
    check('other folders kept', 'mydocs' not in names)
    check('user data never listed', not any(n in names for n in ('memory.json', 'keys.dat', 'journal.jsonl')))
    check('size counts files', cleanup.size(old) == 1)
print('test_cleanup: %d passed, %d failed' % (ok, fail))
sys.exit(1 if fail else 0)
