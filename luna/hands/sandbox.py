"""Where a confirmed development command actually runs: in a Windows Job Object, with hard limits.

What this gives (pure standard library, ctypes; no administrator rights):
  - every process the command starts (npm -> node -> ..., pytest workers, a forgotten server) belongs to one job; when the command ends,
    times out or the program closes, the whole tree is killed, not only the first process;
  - a cap on the number of processes (a fork bomb stops) and on the memory of the whole tree;
  - the command cannot touch the clipboard, change system or display settings, log the user off, or use global atoms;
  - the output is read with a size cap while it is produced (a command that prints gigabytes is stopped, not buffered);
  - the command starts suspended and is put into the job before its first instruction, so nothing escapes in the gap.

What it does NOT give: a file-system or network wall. A command can still read and write what the user's account can (that is the work it is
for); what protects the files is that it only runs after the creator reads the plate and presses Run, from a fixed list of tools (runner.py).
On other systems the limits are not available: the command is still run with the timeout and the output cap."""
import os
import subprocess
import threading
import time

MAX_PROCESSES = 128
MAX_MEMORY = 8 << 30   # a big build (dotnet, cargo, Unity tooling) may use a lot; this only stops a runaway
MAX_BYTES = 4 << 20          # read at most this much output; the runner cuts it further for her
STATUS_NO_JOB = 'nojob'

_JOB_FLAGS = 0x8 | 0x200 | 0x2000   # active process limit | job memory limit | kill on job close
_UI_FLAGS = 0x2 | 0x4 | 0x8 | 0x10 | 0x20 | 0x40 | 0x80   # read/write clipboard, system parameters, display settings, atoms, desktops, exit windows
_CREATE_SUSPENDED = 0x4
_CREATE_NO_WINDOW = 0x08000000


def _make_job(max_processes, max_memory):
    """-> the job handle with the limits set, or None when this system cannot (not Windows, or the call failed)."""
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ('r_ops', 'w_ops', 'o_ops', 'r_bytes', 'w_bytes', 'o_bytes')]

    class Basic(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong), ('LimitFlags', wintypes.DWORD),
                    ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [('Basic', Basic), ('Io', IoCounters), ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

    class UiLimits(ctypes.Structure):
        _fields_ = [('UIRestrictionsClass', wintypes.DWORD)]

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    job = k32.CreateJobObjectW(None, None)
    if not job:
        return None
    ext = Extended()
    ext.Basic.LimitFlags = _JOB_FLAGS
    ext.Basic.ActiveProcessLimit = max_processes
    ext.JobMemoryLimit = max_memory
    ui = UiLimits(_UI_FLAGS)
    if not (k32.SetInformationJobObject(job, 9, ctypes.byref(ext), ctypes.sizeof(ext))
            and k32.SetInformationJobObject(job, 4, ctypes.byref(ui), ctypes.sizeof(ui))):
        k32.CloseHandle(job)
        return None
    return job


def _kernel():
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    nt = ctypes.WinDLL('ntdll')
    nt.NtResumeProcess.argtypes = [wintypes.HANDLE]
    return k32, nt


def run(argv, cwd, env, timeout, max_bytes=MAX_BYTES, max_processes=MAX_PROCESSES, max_memory=MAX_MEMORY):
    """Run argv (no shell) and wait -> (exit code or None, output bytes (stdout+stderr), error: '' | 'timeout' | 'toomuch').
    Raises OSError when the program cannot be started."""
    job = _make_job(max_processes, max_memory)
    flags = _CREATE_NO_WINDOW if os.name == 'nt' else 0
    if job:
        flags |= _CREATE_SUSPENDED
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)
    k32 = nt = None
    if job:
        k32, nt = _kernel()
        handle = int(proc._handle)   # noqa: SLF001 - the only way to get the process handle from Popen
        if not k32.AssignProcessToJobObject(job, handle):   # (e.g. the program already runs in a job that forbids it)
            proc.kill()
            proc.wait()
            k32.CloseHandle(job)
            raise OSError('job')
        nt.NtResumeProcess(handle)

    chunks, size, state = [], [0], {'over': False}

    def pump():
        while True:
            block = proc.stdout.read(8192)
            if not block:
                return
            if size[0] < max_bytes:
                chunks.append(block[:max_bytes - size[0]])
            size[0] += len(block)
            if size[0] > max_bytes * 2:   # far beyond what anyone reads: stop the command, do not just ignore it
                state['over'] = True
                return

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    while proc.poll() is None and not state['over'] and time.monotonic() < deadline:
        time.sleep(0.05)
    error = 'toomuch' if state['over'] else 'timeout' if proc.poll() is None else ''
    if job:
        k32.TerminateJobObject(job, 1)   # the whole tree: on a timeout or too much output, and the forgotten leftovers of a finished command
    if error:
        proc.kill()
    code = None if error else proc.wait()
    if error:
        proc.wait()
    reader.join(2)   # the pipe closes when the tree is gone; without a job a leftover may keep it open: then what was read is enough
    try:
        proc.stdout.close()
    except OSError:
        pass
    if job:
        k32.CloseHandle(job)
    return code, b''.join(chunks), error
