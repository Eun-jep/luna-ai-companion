"""pytest set-up.

The old tests (tests/test_*.py) are scripts: they run at import time and print PASS / FAIL lines. pytest must NOT import them, so they are
ignored here and are run by tests/native/test_legacy_scripts.py, one subprocess per script (exactly what tests/run_all.py does). New tests are
ordinary pytest functions in tests/native/."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault('LUNA_TEST', '1')   # paths.py then uses a throw-away data folder: a test never touches the real data

collect_ignore_glob = ['test_*.py']       # only the files directly in tests/ (the native ones live one folder deeper)
