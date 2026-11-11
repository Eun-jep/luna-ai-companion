"""Runs every old script-style test (tests/test_*.py) as one pytest item, in its own process, and fails on any FAIL line or non-zero exit.

    pytest tests/native -m "not slow"     only the fast native tests
    pytest tests/native -k journal        only the old script(s) with "journal" in the name
    pytest -n auto                        (with pytest-xdist) the old scripts in parallel
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent.parent
SCRIPTS = sorted(p for p in TESTS.glob('test_*.py'))
try:
    BASELINE = json.loads((TESTS / 'legacy_counts.json').read_text(encoding='utf-8'))   # PASS lines each script printed when recorded
except (OSError, ValueError):
    BASELINE = {}


@pytest.mark.slow
@pytest.mark.parametrize('script', SCRIPTS, ids=lambda p: p.stem)
def test_script(script):
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONDONTWRITEBYTECODE'}
    done = subprocess.run([sys.executable, '-X', 'utf8', str(script)], capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=900, env=env, cwd=str(TESTS.parent))
    lines = done.stdout.splitlines()
    failed = [line for line in lines if line.startswith('FAIL')]
    passed = sum(line.startswith('PASS') for line in lines)
    assert not failed, '\n'.join(failed[:20])
    assert done.returncode == 0, 'exit %d after %d PASS lines\n%s' % (done.returncode, passed, (done.stderr or done.stdout)[-1500:])
    expected = BASELINE.get(script.stem)
    assert expected is None or passed >= expected, \
        '%s printed %d PASS lines, the baseline is %d: checks were lost (if on purpose: python tools/legacy_counts.py)' % (script.stem, passed, expected)
