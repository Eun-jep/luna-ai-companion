"""Clean up the junk this program leaves behind. Nothing of the user's is touched.

    py cleanup.py            show what would be removed and how much room it takes (removes nothing)
    py cleanup.py --apply    remove it

What counts as junk: Python caches (__pycache__), unfinished downloads in models/, old log files in this folder, and the temporary
folders that Python makes in the system temp folder (names like tmpab12cd_e, older than a day - the tests leave them behind).
NOT touched: memory, keys, journal, backups used by Undo, models, documents, projects."""
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DAY = 24 * 3600
TMP_NAME = re.compile(r'^tmp[a-z0-9_]{8}$')


def size(path):
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())


def candidates():
    """-> [(path, why)]"""
    found = []
    for d in HERE.rglob('__pycache__'):
        if 'node_modules' not in d.parts:
            found.append((d, 'Python cache'))
    models = HERE / 'models'
    if models.is_dir():
        for f in models.rglob('*'):
            if f.is_file() and f.suffix in ('.part', '.tmp', '.zip', '.bz2', '.gz') and f.name.endswith(('.zip', '.tar.bz2', '.part', '.tmp')):
                found.append((f, 'leftover download'))
    for f in HERE.glob('*.log'):
        if time.time() - f.stat().st_mtime > 7 * DAY:
            found.append((f, 'old log'))
    temp = Path(tempfile.gettempdir())
    for d in temp.glob('tmp*'):
        try:
            if d.is_dir() and TMP_NAME.match(d.name) and time.time() - d.stat().st_mtime > DAY:
                found.append((d, 'temporary folder'))
        except OSError:
            pass
    return found


def main(apply=False):
    found = candidates()
    total, removed, failed = 0, 0, 0
    for path, why in found:
        try:
            n = size(path)
        except OSError:
            continue
        total += n
        if apply:
            try:
                shutil.rmtree(path) if path.is_dir() else path.unlink()
                removed += n
            except OSError:
                failed += 1
    mb = lambda n: '%.1f MB' % (n / 1048576)
    kinds = {}
    for _, why in found:
        kinds[why] = kinds.get(why, 0) + 1
    for why, n in sorted(kinds.items()):
        print('  %-20s %d' % (why, n))
    if apply:
        print('Removed %s%s.' % (mb(removed), ' (%d could not be removed, they are in use)' % failed if failed else ''))
    else:
        print('Would free %s. Run "py cleanup.py --apply" to remove it.' % mb(total))
    return total


if __name__ == '__main__':
    main('--apply' in sys.argv)
