"""Running a development command in a project: build, test, run a script, look at the git state.

She asks with [run:command]; the creator sees the exact command and the folder on a plate and presses Run (single use, two minutes).
No shell: the command is split into words and only well-known development tools with safe sub-commands are accepted; characters that
chain, redirect or expand are refused. The folder is the project of the file she was last shown. Output is cut and goes back to her
as a message; the program's environment is stripped of keys and tokens first. Pure standard library."""
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import devtools

TTL = 120
TIMEOUT = 90
MAX_OUT = 6000
PENDING = {}          # token -> (args, cwd, time)
LAST = {}             # the command she last ran with his press: (args, cwd), for the "run it again" step of fixing a bug

# tool -> allowed first words (None: any arguments are fine, the tool only compiles or runs what is in the project)
TOOLS = {
    'python': None, 'py': None, 'pytest': None, 'node': None, 'tsc': None,
    'npm': {'test', 'run', 'ci', 'install', 'start', 'build', '--version'},
    'git': {'status', 'diff', 'log', 'branch', 'show', '--version'},
    'dotnet': {'build', 'test', 'run', 'restore', 'clean', '--version', '--info'},
    'cargo': {'build', 'test', 'run', 'check', 'clippy', 'fmt', '--version'},
    'go': {'build', 'test', 'run', 'vet', 'fmt', 'version'},
}
BAD_CHARS = re.compile(r'[&|<>;`$%^\n\r\x00]')
BAD_ARGS = re.compile(r'^(-c|-m\s*pip|--exec|-e|--eval|-p|--print)$', re.I)
SECRET_ENV = re.compile(r'key|token|secret|password|passwd|credential|auth', re.I)
MARKERS = ('.git', 'package.json', 'pyproject.toml', 'setup.py', 'requirements.txt', 'Cargo.toml', 'go.mod')
MARKER_EXT = ('.sln', '.csproj', '.uproject', '.godot')


def project_dir():
    """The project of the file she was last shown (its nearest parent with a project marker, else the file's own folder), or None."""
    shown = sorted(devtools.GRANTED.values(), key=lambda g: g['t'])
    if not shown or time.time() - shown[-1]['t'] > devtools.GRANT_TTL:
        return None
    here = Path(shown[-1]['path']).resolve().parent
    for d in [here, *list(here.parents)[:6]]:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        if any(m in names for m in MARKERS) or any(n.lower().endswith(MARKER_EXT) for n in names):
            return d
    return here if here.is_dir() else None


def parse(text):
    """The command as a list of words, or ValueError('refused'|'tool')."""
    text = str(text or '').strip()
    if not 1 <= len(text) <= 160 or BAD_CHARS.search(text):
        raise ValueError('refused')
    words = re.findall(r'"[^"]*"|\S+', text)
    words = [w[1:-1] if len(w) > 1 and w[0] == '"' and w[-1] == '"' else w for w in words]
    tool = words[0].lower().removesuffix('.exe').removesuffix('.cmd')
    if tool not in TOOLS or any(BAD_ARGS.match(w) for w in words[1:]):
        raise ValueError('tool')
    if tool in ('python', 'py') and '-m' in words[1:3] and words[words.index('-m') + 1:words.index('-m') + 2] not in (['pytest'], ['unittest'], ['compileall']):
        raise ValueError('tool')   # -m runs any installed module (pip among them): only the test runners and the compiler check
    subs = TOOLS[tool]
    if subs is not None and (len(words) < 2 or words[1].lower() not in subs):
        raise ValueError('tool')
    if tool == 'git' and any(w.startswith(('--output', '--ext-diff', '-c', '--exec')) for w in words[2:]):
        raise ValueError('refused')
    return [tool] + words[1:]


def propose(text):
    """-> a plate {'token','cmd','where'} for the creator, or {'fail': 'refused'|'tool'|'nocwd'}."""
    try:
        args = parse(text)
    except ValueError as exc:
        return {'fail': str(exc)}
    cwd = project_dir()
    if not cwd:
        return {'fail': 'nocwd'}
    now = time.time()
    for k in [k for k, v in PENDING.items() if now - v[2] > TTL]:
        del PENDING[k]
    token = secrets.token_hex(8)
    PENDING[token] = (args, str(cwd), now)
    return {'token': token, 'cmd': ' '.join(args), 'where': str(cwd)}


def take(token):
    entry = PENDING.pop(token, None) if isinstance(token, str) else None
    entry = entry if entry and time.time() - entry[2] <= TTL else None
    if entry:
        LAST['run'] = (entry[0], entry[1], time.time())
    return entry


def again():
    """The last confirmed command, ready to run in the same folder -> an entry for run(), or None (nothing run yet, or too long ago)."""
    last = LAST.get('run')
    if not last or time.time() - last[2] > devtools.GRANT_TTL:
        return None
    return (last[0], last[1], time.time())


def run(entry):
    """Run the confirmed command -> {'ok', 'code', 'text', 'cmd'}; never raises."""
    args, cwd, _ = entry
    exe = shutil.which(args[0])
    if not exe:
        return {'ok': False, 'code': None, 'text': '', 'cmd': ' '.join(args), 'error': 'missing'}
    env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
    try:
        done = subprocess.run([exe] + args[1:], cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT,
                              creationflags=0x08000000 if os.name == 'nt' else 0)
        out = (done.stdout + done.stderr).decode('utf-8', errors='replace')
        code, error = done.returncode, ''
    except subprocess.TimeoutExpired as exc:
        out = ((exc.stdout or b'') + (exc.stderr or b'')).decode('utf-8', errors='replace')
        code, error = None, 'timeout'
    except OSError:
        return {'ok': False, 'code': None, 'text': '', 'cmd': ' '.join(args), 'error': 'failed'}
    out = out.strip()
    if len(out) > MAX_OUT:
        out = out[:MAX_OUT // 3] + '\n...\n' + out[-MAX_OUT * 2 // 3:]
    return {'ok': code == 0, 'code': code, 'text': out, 'cmd': ' '.join(args), 'error': error}
