"""Reading a log: secrets masked, a long log boiled down to its problems and its end, logs never editable (devtools.py)."""
import os
import sys, tempfile, pathlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import devtools
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

short = 'ok start\npassword=hunter22xyz\nAuthorization: Bearer abcdef123456\n'
d = devtools.digest_log(short)
ok('a short log stays whole', 'ok start' in d and 'Выжимка' not in d)
ok('passwords and bearer tokens are masked', 'hunter22xyz' not in d and 'abcdef123456' not in d and '***' in d)
ok('a long random key is masked', 'A' * 40 not in devtools.mask_secrets('key ' + 'A' * 40 + ' end'))

lines = []
for i in range(3000):
    lines.append('2026-11-03 10:%02d:%02d INFO request %d served in %d ms' % (i // 60 % 60, i % 60, i, 20 + i % 7))
    if i % 100 == 0:
        lines.append('2026-11-03 10:00:%02d ERROR db timeout after %d s on host 10.0.0.%d' % (i % 60, 30 + i % 3, i % 9))
lines.insert(1500, 'Traceback (most recent call last):')
lines.insert(1501, 'ValueError: bad value')
lines.append('2026-11-03 11:00:00 INFO shutdown')
big = '\n'.join(lines)
d = devtools.digest_log(big)
ok('a long log is shortened', len(big) > devtools.MAX_SEND_CHARS and len(d) <= devtools.MAX_SEND_CHARS and 'Выжимка' in d)
ok('the same error with other numbers is counted once', d.count('db timeout') >= 1 and 'встретилось 30 раз' in d)
ok('the rare traceback is kept', 'Traceback' in d and 'ValueError' in d)
ok('the end of the log is kept', 'shutdown' in d and 'Конец лога' in d)
ok('routine lines are not listed', d.count('served in') < 40)

tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / 'app.log').write_text(big, encoding='utf-8')
devtools.FOUND['t1'] = {'path': str(tmp / 'app.log'), 'label': 'app.log', 't': 9e18}
r = devtools.read_code('t1')
ok('read_code gives the digest of a log', r['digest'] is True and 'Выжимка' in r['text'])
ok('a log is never granted for editing', 'app.log' not in devtools.GRANTED)
ok('.log is readable by name', '.log' in devtools.CODE_EXT and 'logs' not in devtools.CODE_SKIP)
