"""A missing optional library is reported in plain words and switches its feature off; it never takes the app down."""
import importlib
import re
import sys
from pathlib import Path

from luna.core import deps

ROOT = Path(__file__).resolve().parent.parent.parent


def test_everything_present_gives_an_empty_report():
    assert deps.report(find=lambda name: object()) == ''
    assert deps.missing(find=lambda name: object()) == []


def test_missing_libraries_are_named_with_the_install_command():
    text = deps.report(find=lambda name: None if name == 'numpy' else object())
    assert 'numpy' in text and 'hearing' in text
    assert 'pip install -r requirements.txt' in text
    assert 'sounddevice' not in text


def test_every_listed_library_is_in_requirements():
    wanted = (ROOT / 'requirements.txt').read_text(encoding='utf-8').lower()
    for module, (pip, _why) in deps.LIBS.items():
        assert pip.lower() in wanted, module


def test_hearing_and_songid_import_without_numpy_and_report_themselves_off(monkeypatch):
    saved = {k: sys.modules.get(k) for k in ('numpy', 'luna.senses.hearing', 'luna.senses.songid')}
    monkeypatch.setitem(sys.modules, 'numpy', None)   # `import numpy` now raises ImportError
    for name in ('luna.senses.hearing', 'luna.senses.songid'):
        sys.modules.pop(name, None)
    try:
        hearing = importlib.import_module('luna.senses.hearing')
        songid = importlib.import_module('luna.senses.songid')
        assert hearing.np is None
        assert hearing.available() == {'capture': False, 'asr': False}
        assert songid.available() is False
    finally:   # leave the real modules for the other tests of this worker
        for name in ('luna.senses.hearing', 'luna.senses.songid'):
            sys.modules.pop(name, None)
        monkeypatch.undo()
        for name in ('luna.senses.hearing', 'luna.senses.songid'):
            if saved[name] is not None:
                sys.modules[name] = saved[name]


def test_the_desktop_shell_starts_the_projects_own_python_and_keeps_a_log():
    main = (ROOT / 'desktop' / 'main.js').read_text(encoding='utf-8')
    assert re.search(r"\.venv.*python\.exe", main), 'the shell must prefer .venv: the system Python has no libraries'
    assert 'shell.log' in main and 'showErrorBox' in main
