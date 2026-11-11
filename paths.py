"""Where Luna keeps the user's own data (memory, keys, journal, settings of the window, song library ...).

The data lives OUTSIDE the project folder, in  %APPDATA%\\Luna  (or ~/.luna when there is no APPDATA), so that it can never end up in an archive,
a repository or a copy of the program by accident. The folder can be changed with the environment variable LUNA_DATA_DIR.

While a test script runs (file name test_*.py, pytest, or LUNA_TEST is set) a throw-away temporary folder is used instead: a test can never read,
write or move the real data. Importing this module creates nothing but the (empty) data folder; moving files from the old location is done only
by migrate(), which the application calls once at start-up.

Pure standard library."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent   # the program folder (code, web page, models), never user data

# names of the files and folders that used to live next to the program and now live in DATA_DIR
LEGACY = ('memory.json', 'memory-backups', 'journal.jsonl', 'keys.dat', 'providers.json', 'ui-state.json', 'actions.json',
          'edit_backups', 'songs', 'project_manifests', 'workspaces.json', 'habits.json', 'manners.json', 'lists.json', 'standup.json', 'settings.local.json')


def under_test():
    """True while a test is running."""
    if os.environ.get('LUNA_TEST') or 'pytest' in sys.modules:
        return True
    return os.path.basename(sys.argv[0] if sys.argv else '').startswith('test_')


def _default_dir():
    if os.environ.get('LUNA_DATA_DIR'):
        return Path(os.environ['LUNA_DATA_DIR'])
    if under_test():
        return Path(tempfile.mkdtemp(prefix='luna-data-'))
    base = os.environ.get('APPDATA')
    return Path(base) / 'Luna' if base else Path.home() / '.luna'


DATA_DIR = _default_dir()
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass   # a read-only place: the writers report their own errors


def data_file(name):
    """The place of one data file or folder (not created)."""
    return DATA_DIR / name


def seed(name, template):
    """Give a first-run copy of a template file (shipped with the program) to the data folder if the user has no such file yet."""
    target, template = DATA_DIR / name, Path(template)
    if not target.exists() and template.is_file():
        try:
            shutil.copyfile(template, target)
            return True
        except OSError:
            return False
    return False


def migrate(source=ROOT, target=None):
    """Move user data that an older version left next to the program into the data folder. Nothing is ever overwritten: if the target already
    exists the old one stays where it is. Returns the list of names that were moved."""
    target = Path(target) if target is not None else DATA_DIR
    if under_test() and target == DATA_DIR and not os.environ.get('LUNA_DATA_DIR'):
        return []   # a test must never move the real files
    moved = []
    for name in LEGACY:
        old, new = Path(source) / name, target / name
        if not old.exists() or new.exists():
            continue
        try:
            target.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old), str(new))
            moved.append(name)
        except OSError as exc:
            print('Could not move %s to %s: %s' % (name, target, exc))
    if moved:
        print('Your data now lives in %s (moved: %s)' % (target, ', '.join(moved)))
    return moved
