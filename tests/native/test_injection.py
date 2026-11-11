"""Text that does not come from the creator (files, clipboard, diffs, web) is data: it is neutralized and it taints the round."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
PY = (ROOT / 'app.py').read_text(encoding='utf-8') + (ROOT / 'luna' / 'server' / 'hands.py').read_text(encoding='utf-8') + (ROOT / 'luna' / 'server' / 'chat.py').read_text(encoding='utf-8')


def body(name):
    m = re.search(r'(?:async )?function %s\b.*?\n}\n' % name, JS, re.S)
    assert m, name
    return m.group(0)


def test_every_outside_text_taints_the_next_round():
    for fn in ('readFile', 'readDoc', 'askClip', 'askScan', 'askDiff', 'askSql'):
        assert 'webRound = 2' in body(fn), fn


def test_clipboard_cannot_close_its_code_fence():
    assert '.replace(/`{3,}/g' in body('askClip')


def test_server_neutralizes_file_doc_diff_and_web_text():
    assert PY.count('security.neutralize(') >= 4
    for call in ("devtools.read_code(", "gitdiff.run(", "docfiles.read("):
        i = PY.index(call)
        assert 'security.neutralize(shown' in PY[i:i + 400], call
