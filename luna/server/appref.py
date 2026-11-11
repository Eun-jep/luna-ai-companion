"""The running application module (app.py is `__main__` when started by hand, `app` when imported), late-bound: what a test patches in it is seen here."""
import sys


def _app():
    main = sys.modules.get('__main__')
    return main if hasattr(main, 'Handler') else sys.modules['app']
