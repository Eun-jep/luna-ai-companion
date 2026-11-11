"""Stack traces and test runs are read by the program: exception, root cause, frame in his own code, usual cause, failed tests."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import traces as T
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

PY = r'''Traceback (most recent call last):
  File "C:\work\shop\app\main.py", line 42, in handle
    total = price(order)
  File "C:\work\shop\app\pricing.py", line 7, in price
    return order["items"][0]["cost"] * 2
  File "C:\Python312\Lib\site-packages\lib\x.py", line 3, in helper
    return d["cost"]
KeyError: 'cost'
'''
f = T.detect(PY)
ok('python: one trace, exception and message', len(f) == 1 and f[0]['exc'] == 'KeyError' and f[0]['msg'] == "'cost'" and len(f[0]['frames']) == 3)
c = T.culprit(f[0])
ok('python: the culprit is the innermost frame in his code, not the library', c[0].endswith('pricing.py') and c[1] == 7 and c[2] == 'price')
r = T.analyze('Вот что падает:\n' + PY)
ok('python: the analysis names file, line and the usual cause', 'pricing.py:7' in r and 'KeyError' in r and 'ключу или индексу' in r)

NONE = 'Traceback (most recent call last):\n  File "/home/u/app.py", line 3, in <module>\n    x.strip()\nAttributeError: \'NoneType\' object has no attribute \'strip\'\n'
ok('python: NoneType gets its own advice', 'пустое значение' in T.analyze('помоги ' + NONE))

JAVA = '''Exception in thread "main" java.lang.IllegalStateException: failed to start
\tat com.acme.shop.App.run(App.java:55)
\tat com.acme.shop.Main.main(Main.java:10)
Caused by: java.lang.NullPointerException: Cannot invoke "String.length()" because "s" is null
\tat java.base/java.util.Objects.requireNonNull(Objects.java:208)
\tat com.acme.shop.Util.size(Util.java:21)
\t... 2 more
'''
f = T.detect(JAVA)
ok('java: the exception and its cause are both found', [t['exc'] for t in f] == ['java.lang.IllegalStateException', 'java.lang.NullPointerException'] and f[1]['caused'])
ok('java: the library frame is skipped for the culprit', T.culprit(f[1])[0] == 'Util.java' and T.culprit(f[1])[1] == 21)

JS = r'''TypeError: Cannot read properties of undefined (reading 'id')
    at getUser (C:\proj\src\user.js:14:20)
    at Layer.handle [as handle_request] (C:\proj\node_modules\express\lib\router\layer.js:95:5)
'''
f = T.detect(JS)
ok('js: the frame in his code, not node_modules', f and T.culprit(f[0])[0].endswith('user.js') and T.culprit(f[0])[1] == 14)
ok('js: undefined property is the null case', 'пустое значение' in T.advice(f[0]))

NET = r'''System.NullReferenceException: Object reference not set to an instance of an object.
   at System.Linq.Enumerable.Select[TSource,TResult](IEnumerable`1 source)
   at Shop.OrderService.Total(Order o) in C:\src\Shop\OrderService.cs:line 88
'''
f = T.detect(NET)
ok('.net: path and line of his code', f and T.culprit(f[0])[0].endswith('OrderService.cs') and T.culprit(f[0])[1] == 88)

GO = 'panic: runtime error: index out of range [3] with length 3\n\ngoroutine 1 [running]:\nmain.pick(...)\n\t/home/u/proj/main.go:12 +0x1d\nmain.main()\n\t/home/u/proj/main.go:20 +0x2a\n'
f = T.detect(GO)
ok('go: panic with its frame', f and f[0]['lang'] == 'Go' and T.culprit(f[0])[1] == 12)
RUST = "thread 'main' panicked at src/main.rs:5:10:\ncalled `Option::unwrap()` on a `None` value\n"
f = T.detect(RUST)
ok('rust: panic place and message', f and f[0]['frames'][0][:2] == ('src/main.rs', 5) and 'unwrap' in f[0]['msg'])

LIBONLY = 'Traceback (most recent call last):\n  File "/usr/lib/python3/site-packages/x.py", line 1, in f\n    pass\nValueError: bad\n'
ok('a trace with no code of his is said so', 'нет его кода' in T.analyze('вот ' + LIBONLY + ' это всё'))

PYTEST = '''============ short test summary info ============
FAILED tests/test_a.py::test_one - AssertionError: assert 1 == 2
FAILED tests/test_b.py::test_two - KeyError: 'x'
========= 2 failed, 8 passed, 1 skipped in 3.21s =========
'''
s = T.test_summary(PYTEST)
ok('pytest: counts and failed tests', 'провалено 2' in s and 'прошло 8' in s and 'tests/test_a.py::test_one' in s and 'assert 1 == 2' in s)
JEST = 'Tests:       1 failed, 9 passed, 10 total\n  ● Cart › adds item\n'
ok('jest: counts and failed names', 'Cart › adds item' in T.test_summary(JEST) and '1 failed' in T.test_summary(JEST))
ok('dotnet and go summaries', '2' in T.test_summary('Failed!  - Failed: 2, Passed: 8, Skipped: 0, Total: 10') and 'TestX' in T.test_summary('--- FAIL: TestX (0.00s)\nFAIL'))
ok('ordinary talk is left alone', T.analyze('привет, как дела? расскажи про свой день, мне интересно что было') == '' and T.analyze('коротко') == '')
ok('a secret in the message of the error is masked', 'hunter2hunter2' not in T.analyze('Traceback (most recent call last):\n  File "/a/b.py", line 1, in f\n    pass\nRuntimeError: login password=hunter2hunter2 rejected\n'))
big = PY * 10 + PYTEST
ok('the analysis fits next to the message', len(T.analyze(big)) <= 2600 and T.analyze(big).count('Python: KeyError') == 1)
