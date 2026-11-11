"""Her hands, part 3: press keys and move the mouse (Windows, stdlib ctypes only).
Everything here is strict by design: a fixed vocabulary of actions, a fixed list of allowed keys, and no way to
run a command. It is only reached through a started, confirmed task (see app.py)."""
import ctypes
import sys
import time
from ctypes import wintypes

WINDOWS = sys.platform == 'win32'
DRY = False   # tests: describe instead of pressing

if WINDOWS:
    user32 = ctypes.windll.user32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # real pixels, so screenshot fractions land where intended
    except (OSError, AttributeError):
        user32.SetProcessDPIAware()

    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                    ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                    ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]

    class _U(ctypes.Union):
        _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [('type', wintypes.DWORD), ('u', _U)]

MOUSE_FLAGS = {'left': (0x0002, 0x0004), 'right': (0x0008, 0x0010), 'middle': (0x0020, 0x0040)}
WHEEL, KEYUP, UNICODE = 0x0800, 0x0002, 0x0004

# The only keys she may press. No Windows key (no Run dialog, no shell shortcuts), no Alt+F4, no function keys.
KEYS = {'enter': 0x0D, 'tab': 0x09, 'esc': 0x1B, 'escape': 0x1B, 'backspace': 0x08, 'delete': 0x2E, 'space': 0x20,
        'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27, 'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
        'ctrl': 0x11, 'shift': 0x10, 'alt': 0x12}
LETTER_COMBOS = set('acvxzysfnotwprh')   # with Ctrl: select all, copy, paste, cut, undo, redo, save, find, new, open, tab, close, print, ...
MODIFIERS = ('ctrl', 'shift', 'alt')


def screen_size():
    return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)) if WINDOWS else (1920, 1080)


def cursor():
    if not WINDOWS:
        return (0, 0)
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def to_pixels(x, y):
    """Screenshot fractions 0..1000 -> real screen pixels (clamped inside the screen)."""
    w, h = screen_size()
    return (min(w - 1, max(0, round(float(x) / 1000 * w))), min(h - 1, max(0, round(float(y) / 1000 * h))))


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _mouse(flags, data=0):
    return INPUT(0, _U(mi=MOUSEINPUT(0, 0, data, flags, 0, 0)))


def _key(vk=0, scan=0, flags=0):
    return INPUT(1, _U(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))


def move(x, y):
    px, py = to_pixels(x, y)
    if not DRY and WINDOWS:
        user32.SetCursorPos(px, py)
    return px, py


def click(x, y, button='left', count=1):
    px, py = move(x, y)
    if DRY or not WINDOWS:
        return px, py
    down, up = MOUSE_FLAGS[button]
    time.sleep(0.08)
    for _ in range(count):
        _send(_mouse(down))
        time.sleep(0.03)
        _send(_mouse(up))
        time.sleep(0.06)
    return px, py


def scroll(x, y, amount):
    px, py = move(x, y)
    if not DRY and WINDOWS:
        time.sleep(0.05)
        _send(_mouse(WHEEL, (int(amount) * 120) & 0xFFFFFFFF))
    return px, py


def type_text(text):
    if DRY or not WINDOWS:
        return
    for ch in text:
        if ch == '\n':
            press('enter')
            continue
        raw = ch.encode('utf-16-le')
        units = [int.from_bytes(raw[i:i + 2], 'little') for i in range(0, len(raw), 2)]
        for u in units:
            _send(_key(0, u, UNICODE), _key(0, u, UNICODE | KEYUP))
        time.sleep(0.015)


def parse_combo(combo):
    """'ctrl+a' -> ['ctrl', 'a']; None when the combination is not on the allowed list."""
    parts = [p.strip().lower() for p in str(combo).split('+') if p.strip()]
    if not 1 <= len(parts) <= 3:
        return None
    *mods, last = parts
    if any(m not in MODIFIERS for m in mods) or len(set(mods)) != len(mods):
        return None
    if last in KEYS and last not in MODIFIERS:
        if 'alt' in mods:
            return None   # Alt+anything is how windows get closed and menus hijacked
        return parts
    if len(last) == 1 and last in LETTER_COMBOS and mods == ['ctrl']:
        return parts
    return None


def press(combo):
    parts = parse_combo(combo)
    if parts is None:
        raise ValueError('key')
    if DRY or not WINDOWS:
        return
    vks = [KEYS[p] if p in KEYS else ord(p.upper()) for p in parts]
    _send(*[_key(v) for v in vks])
    time.sleep(0.03)
    _send(*[_key(v, flags=KEYUP) for v in reversed(vks)])
