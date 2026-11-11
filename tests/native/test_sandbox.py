"""The sandbox around her commands (luna/hands/sandbox.py): the whole process tree dies, output and memory and process count are capped."""
import os
import sys
import time

import pytest

from luna.hands import runner, sandbox

PY = sys.executable
windows_only = pytest.mark.skipif(os.name != 'nt', reason='Job Objects are Windows only')


def run(code, **kw):
    kw.setdefault('timeout', 20)
    return sandbox.run([PY, '-c', code], os.getcwd(), dict(os.environ), **kw)


def test_normal_command_returns_code_and_output():
    code, out, error = run('import sys; print("hello"); print("oops", file=sys.stderr); sys.exit(3)')
    assert code == 3 and error == '' and b'hello' in out and b'oops' in out


def test_timeout_stops_the_command():
    start = time.monotonic()
    code, _, error = run('import time; time.sleep(60)', timeout=1)
    assert code is None and error == 'timeout' and time.monotonic() - start < 10


def test_huge_output_is_stopped_not_buffered():
    start = time.monotonic()
    code, out, error = run('import sys\nwhile True: sys.stdout.write("x" * 100000)', max_bytes=100000)
    assert error == 'toomuch' and len(out) <= 100000 and time.monotonic() - start < 15


@windows_only
def test_grandchildren_die_with_the_timeout(tmp_path):
    marker = tmp_path / 'still_alive.txt'
    child = 'import time, pathlib; time.sleep(4); pathlib.Path(%r).write_text("alive")' % str(marker)
    parent = 'import subprocess, sys, time; subprocess.Popen([sys.executable, "-c", %r]); time.sleep(60)' % child
    _, _, error = run(parent, timeout=1)
    assert error == 'timeout'
    time.sleep(6)
    assert not marker.exists()   # the child was killed with its parent: plain subprocess.run would have left it running


@windows_only
def test_leftover_of_a_finished_command_is_killed(tmp_path):
    marker = tmp_path / 'leftover.txt'
    child = 'import time, pathlib; time.sleep(4); pathlib.Path(%r).write_text("alive")' % str(marker)
    parent = 'import subprocess, sys; subprocess.Popen([sys.executable, "-c", %r]); print("done")' % child   # leaves the child running
    code, out, error = run(parent)
    assert code == 0 and error == '' and b'done' in out
    time.sleep(6)
    assert not marker.exists()


@windows_only
def test_memory_of_the_tree_is_capped():
    code, _, error = run('x = bytearray(900 * 1024 * 1024); print("allocated")', max_memory=300 << 20)
    assert code != 0   # the allocation fails or the tree is killed at the limit


@windows_only
def test_process_count_is_capped():
    code, out, _ = run('import subprocess, sys\n'
                       'ps = []\n'
                       'try:\n'
                       '    for i in range(12): ps.append(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"]))\n'
                       '    print("all started")\n'
                       'except OSError:\n'
                       '    print("refused")\n'
                       'for p in ps: p.kill()', max_processes=5)
    assert b'refused' in out and b'all started' not in out


def test_missing_program_raises_oserror():
    with pytest.raises(OSError):
        sandbox.run(['definitely-not-a-program-xyz'], os.getcwd(), dict(os.environ), 5)


def test_too_broad_folders_are_refused(tmp_path):
    assert runner.too_broad(os.path.abspath(os.sep))
    assert runner.too_broad(os.path.expanduser('~'))
    assert runner.too_broad(os.path.join(os.path.expanduser('~'), 'Desktop'))
    if os.environ.get('SystemRoot'):
        assert runner.too_broad(os.path.join(os.environ['SystemRoot'], 'System32'))
    assert not runner.too_broad(tmp_path)


def test_more_secrets_are_stripped_from_the_environment():
    for name in ('DATABASE_URL', 'MY_SESSION_ID', 'GH_TOKEN', 'AWS_SECRET_ACCESS_KEY', 'DB_PWD', 'SOME_COOKIE', 'SENTRY_DSN'):
        assert runner.SECRET_ENV.search(name), name
    for name in ('PATH', 'SystemRoot', 'TEMP', 'APPDATA', 'USERPROFILE', 'HOMEDRIVE', 'PYTHONPATH', 'NODE_ENV'):
        assert not runner.SECRET_ENV.search(name), name
