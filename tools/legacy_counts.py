"""Record how many PASS lines each old script test prints -> tests/legacy_counts.json.
The pytest wrapper (tests/native/test_legacy_scripts.py) then fails a script that prints fewer: a test that quietly stops checking is a bug too.
Run it after you deliberately add or remove checks:  python tools/legacy_counts.py"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent / 'tests'


def count(script):
    done = subprocess.run([sys.executable, '-X', 'utf8', str(script)], capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=900, cwd=str(TESTS.parent))
    lines = done.stdout.splitlines()
    if done.returncode or any(line.startswith('FAIL') for line in lines):
        raise SystemExit('%s does not pass: refusing to record a baseline' % script.name)
    return script.stem, sum(line.startswith('PASS') for line in lines)


if __name__ == '__main__':
    with ThreadPoolExecutor(6) as pool:
        counts = dict(pool.map(count, sorted(TESTS.glob('test_*.py'))))
    (TESTS / 'legacy_counts.json').write_text(json.dumps(counts, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print('recorded %d scripts, %d checks' % (len(counts), sum(counts.values())))
