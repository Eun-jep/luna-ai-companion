"""The journal of her hands: what she actually did on this computer, when, and (where it can be taken back) the way to undo it.
Only executed actions are written (never the text of conversations, never keys or the content of files she was shown).
Undo exists where it is honest: a document she created goes to the Recycle Bin, and the last Unreal operation is undone in the
editor. Opening a site or a program, or working the mouse, cannot be taken back, so those entries have no Undo button."""
import ctypes
import json
import os
import threading
import time
from ctypes import wintypes
from pathlib import Path

import codeedit
import docfiles
import office
import projects
import unreal_bridge

def _journal_file():
    """The real journal, except when a test script is running: tests act as if she did things (keys, documents, scans) and must never
    write into, or push real entries out of, the journal of what she really did. A test gets its own temporary file."""
    import sys
    import tempfile
    if os.path.basename(sys.argv[0] if sys.argv else '').startswith('test_') or os.environ.get('LUNA_TEST'):
        return Path(tempfile.mkdtemp(prefix='luna-journal-')) / 'journal.jsonl'
    return Path(__file__).resolve().parent / 'journal.jsonl'


FILE = _journal_file()
KEEP = 1000
_lock = threading.RLock()

KINDS_RU = {'songid': 'отправила в сервис Shazam отпечаток звука (не сам звук), чтобы узнать песню: он включил это сам', 'open': 'открыла по его просьбе: %s', 'task': 'выполняла задачу мышью и клавиатурой: %s', 'task.end': 'закончила задачу на компьютере (действий: %s)',
            'unreal': 'сделала в Unreal Engine: %s', 'doc': 'создала документ %s', 'docread': 'прочитала твой документ или папку %s (он разрешил)', 'move': 'перенесла файл %s (он подтвердил)', 'read': 'прочитала файл с кодом %s (он разрешил)', 'edit': 'изменила файл с кодом %s (он подтвердил)', 'project': 'создала проект %s (он подтвердил)', 'wsadd': 'ты разрешил ей добавлять файлы в папку %s', 'wsdel': 'ты убрал папку %s из разрешённых',
            'undo': 'отменила своё действие: %s', 'key.set': 'сохранила ключ для %s', 'key.clear': 'удалила ключ для %s', 'provider': 'переключилась на нейросеть %s'}


def _read():
    try:
        return [json.loads(l) for l in FILE.read_text(encoding='utf-8').splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def _write(entries):
    tmp = FILE.with_suffix('.tmp')
    tmp.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in entries), encoding='utf-8')
    tmp.replace(FILE)


def log(kind, x='', ok=True, undo=False, path=None, **private):
    """Append one executed action. x is a short label (a name, never content); path stays on the server."""
    with _lock:
        entries = _read()
        entry = {'id': (entries[-1]['id'] + 1) if entries else 1, 't': int(time.time()), 'kind': kind, 'x': str(x)[:160], 'ok': bool(ok),
                 'undo': bool(undo and ok), 'undone': False}
        if path:
            entry['p'] = str(path)
        entry.update({k: str(v) for k, v in private.items() if k in ('b', 'h')})   # private: backup path and the hash of what she wrote
        entries.append(entry)
        _write(entries[-KEEP:])
        return entry['id']


def listing(limit=60):
    """Newest first, without private fields. 'canUndo' tells the page whether to show the button."""
    with _lock:
        entries = _read()
        last_ue = max((e['id'] for e in entries if e['kind'] == 'unreal' and not e['undone'] and e['undo']), default=0)
        out = []
        for e in reversed(entries[-limit:]):
            can = e['undo'] and not e['undone'] and (e['kind'] != 'unreal' or e['id'] == last_ue)
            out.append({'id': e['id'], 't': e['t'], 'kind': e['kind'], 'x': e['x'], 'ok': e['ok'], 'undone': e['undone'], 'canUndo': can})
        return out


def recent_text(n=3, within=86400):
    """For her prompt: what she really did lately, so she never invents or forgets her own actions."""
    now = time.time()
    rows = [e for e in _read() if now - e['t'] <= within and e['kind'] in KINDS_RU and e['ok']][-n:]
    return [(KINDS_RU[e['kind']] % e['x'] if '%s' in KINDS_RU[e['kind']] else KINDS_RU[e['kind']]) for e in rows]


def clear():
    with _lock:
        _write([])


class _FileOp(ctypes.Structure):
    _fields_ = [('hwnd', wintypes.HWND), ('wFunc', wintypes.UINT), ('pFrom', wintypes.LPCWSTR), ('pTo', wintypes.LPCWSTR),
                ('fFlags', ctypes.c_ushort), ('fAnyOperationsAborted', wintypes.BOOL), ('hNameMappings', ctypes.c_void_p), ('lpszProgressTitle', wintypes.LPCWSTR)]


def _recycle(path):
    """Move a file to the Recycle Bin (it can be restored from there). False if Windows refused."""
    op = _FileOp(None, 3, str(path) + '\0', None, 0x40 | 0x10 | 0x4 | 0x400, False, None, None)   # DELETE, ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.fAnyOperationsAborted


def undo(entry_id, transport=None):
    """Take back one journal entry. Returns {'ok': True} or {'ok': False, 'error': code}."""
    with _lock:
        entries = _read()
        entry = next((e for e in entries if e['id'] == entry_id), None)
        if not entry or entry['undone'] or not entry['undo']:
            return {'ok': False, 'error': 'cannot'}
        if entry['kind'] == 'doc':
            path = Path(entry.get('p', ''))
            folder = (office.FOLDER or office._folder()).resolve()
            if folder not in path.resolve().parents:   # only ever inside her own documents folder
                return {'ok': False, 'error': 'cannot'}
            if path.exists():
                try:
                    done = _recycle(path.resolve())
                except (OSError, AttributeError):
                    done = False
                if not done:
                    return {'ok': False, 'error': 'failed'}
        elif entry['kind'] == 'unreal':
            newest = max(e['id'] for e in entries if e['kind'] == 'unreal' and e['undo'] and not e['undone'])
            if entry['id'] != newest:   # the editor undoes only its latest step
                return {'ok': False, 'error': 'cannot'}
            result = unreal_bridge.undo(transport)
            if not result['ok']:
                return {'ok': False, 'error': result['error']}
        elif entry['kind'] == 'move':
            try:
                docfiles.restore(entry.get('b', ''), entry.get('p', ''))
            except (RuntimeError, OSError) as exc:
                return {'ok': False, 'error': str(exc) if isinstance(exc, RuntimeError) else 'failed'}
        elif entry['kind'] == 'edit':
            try:
                codeedit.restore(entry.get('p', ''), entry.get('b', ''), entry.get('h', ''))
            except RuntimeError as exc:
                return {'ok': False, 'error': str(exc)}
        elif entry['kind'] == 'project':
            try:
                projects.restore(entry.get('b', ''), entry.get('h', ''))
            except RuntimeError as exc:
                return {'ok': False, 'error': str(exc)}
        else:
            return {'ok': False, 'error': 'cannot'}
        entry['undone'] = True
        entries.append({'id': entries[-1]['id'] + 1, 't': int(time.time()), 'kind': 'undo', 'x': entry['x'], 'ok': True, 'undo': False, 'undone': False})
        _write(entries[-KEEP:])
        return {'ok': True}
