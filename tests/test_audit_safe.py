"""A test run never touches the real journal of what she did (a wrong entry there, or real ones pushed out by test noise, is not acceptable)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.core import audit
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
real = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'journal.jsonl')
ok('a test script gets its own temporary journal', os.path.abspath(str(audit.FILE)) != os.path.abspath(real) and 'luna-data-' in str(audit.FILE))
before = os.path.getmtime(real) if os.path.exists(real) else None
i = audit.log('open', 'test entry')
ok('a logged entry lands in the temporary file only', audit.FILE.exists() and i == 1 and (os.path.getmtime(real) if os.path.exists(real) else None) == before)
