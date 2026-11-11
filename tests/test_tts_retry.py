"""A sentence the speech service fails on is retried, so that it is spoken instead of appearing only as a subtitle."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app

ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)
app.time.sleep = lambda s: None
calls = []


class Flaky:
    fail = 2

    class Communicate:
        def __init__(self, *a, **k):
            calls.append(1)

        async def stream(self):
            if len(calls) <= Flaky.fail:
                raise OSError('service hiccup')
            yield {'type': 'audio', 'data': b'ID3ok'}


app.edge_tts = Flaky
ok('two hiccups, then the voice comes', app.synthesize('Привет', 'ru-RU-SvetlanaNeural') == b'ID3ok' and len(calls) == 3)
calls.clear(); Flaky.fail = 99
try:
    app.synthesize('Привет', 'ru-RU-SvetlanaNeural'); raised = False
except OSError:
    raised = True
ok('a service that stays down still fails, after three tries', raised and len(calls) == 3)


class Empty:
    class Communicate:
        def __init__(self, *a, **k):
            calls.append(1)

        async def stream(self):
            yield {'type': 'WordBoundary'}


calls.clear(); app.edge_tts = Empty
ok('empty sound is retried and then reported empty', app.synthesize('...', 'x') == b'' and len(calls) == 3)
