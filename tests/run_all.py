"""Runs every test file in this folder (each in its own process) and prints one summary.
Most tests print PASS / FAIL lines; a few older ones (control, devtools, unreal) only print values and are judged by their exit code.
Usage:  py tests/run_all.py            all tests
        py tests/run_all.py journal    only files whose name contains "journal"
Tests use temporary folders and fake networks: they never touch your memory, keys or files."""
import os
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
only = sys.argv[1:]
env = {k: v for k, v in os.environ.items() if k != 'PYTHONDONTWRITEBYTECODE'}   # cached bytecode: importing edge_tts/aiohttp cold takes minutes on a slow disk
total_pass = total_fail = bad_files = 0
for f in sorted(here.glob('test_*.py')):
    if only and not any(o in f.name for o in only):
        continue
    done = subprocess.run([sys.executable, '-X', 'utf8', str(f)], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900, env=env)
    lines = done.stdout.splitlines()
    ok, fail = sum(l.startswith('PASS') for l in lines), [l for l in lines if l.startswith('FAIL')]
    broken = done.returncode != 0
    total_pass += ok
    total_fail += len(fail)
    bad_files += broken or bool(fail)
    print('%-22s %s  pass=%d fail=%d%s' % (f.name, 'FAIL' if fail or broken else 'ok  ', ok, len(fail), '  (exit %d)' % done.returncode if broken else ''))
    for l in fail:
        print('    ' + l)
    if broken:
        print('    ' + '\n    '.join((done.stderr or '').strip().splitlines()[-6:]))
print('\nTOTAL: %d passed, %d failed, %d files with problems' % (total_pass, total_fail, bad_files))
sys.exit(1 if bad_files else 0)
