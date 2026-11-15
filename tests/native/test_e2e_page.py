"""End to end: the real page in a real browser (Edge, via Playwright) talks to the real server; only the language model is replaced.
Skipped when Playwright or Edge is not installed. Uses a temporary data folder (luna/paths.py), never the user's own."""
import os
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

pw = pytest.importorskip('playwright.sync_api')
import app  # noqa: E402

EDGE = [p for p in (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe') if os.path.exists(p)]
# one xdist worker for the whole file (--dist loadgroup): one server and one browser instead of one per worker, which starved each other of CPU
pytestmark = [pytest.mark.slow, pytest.mark.xdist_group('e2e'), pytest.mark.skipif(not EDGE, reason='Edge is not installed')]
SLOW = 90_000   # ms: a loaded machine (the whole suite runs in parallel) needs far more than the 30 s default to load the page and its libraries


@pytest.fixture(scope='module')
def url():
    saved = app.generate_stream, app.generate
    app.generate_stream = lambda *a, **k: iter(['Привет! ', 'Я тебя слышу.'])
    app.generate = lambda *a, **k: 'Привет! Я тебя слышу.'
    srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield 'http://127.0.0.1:%d/' % srv.server_port
    srv.shutdown()
    srv.server_close()
    app.generate_stream, app.generate = saved   # the fakes must not leak into other tests of this worker


def wait_until(page, js, timeout=SLOW):
    """Poll a JS function from outside. page.wait_for_function(str) evaluates the string inside the page, which the strict CSP (no unsafe-eval) refuses."""
    end = time.monotonic() + timeout / 1000
    while time.monotonic() < end:
        if page.evaluate(js):
            return
        page.wait_for_timeout(200)
    raise AssertionError('timed out waiting for: ' + js)


def new_page(browser):
    page = browser.new_page()
    page.set_default_timeout(SLOW)
    page.set_default_navigation_timeout(SLOW)
    return page


@pytest.fixture(scope='module')
def browser():
    with pw.sync_playwright() as p:
        b = p.chromium.launch(executable_path=EDGE[0], headless=True)
        yield b
        b.close()


# FIRST in the file on purpose: the wizard shows on the first launch only, and every other test that opens the page uses that up.
def test_first_run_wizard_walks_through(browser, url):
    page = new_page(browser)
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url, wait_until='domcontentloaded')
    page.wait_for_selector('#wizard:not([hidden]) #wz-card')
    page.get_by_role('button', name='Русский').click()   # the interface switches language at once
    wait_until(page, "() => document.querySelector('#wz-title').textContent.includes('Луна')")
    page.get_by_role('button', name='Дальше').click()
    page.wait_for_selector('.wz-grid button')
    page.locator('.wz-grid button').first.click()   # choosing an online network asks for its key
    assert page.locator('.wz-key').is_visible()
    page.fill('.wz-key input', '')
    page.click('.wz-key button[type=submit]')   # an empty key is refused and nothing is sent
    assert page.locator('.wz-key .error').inner_text().strip()
    page.get_by_role('button', name='Позже').click()
    page.wait_for_selector('#wizard', state='hidden')
    assert not errors, errors
    page.close()

    # the wizard is for the first launch only: once seen, "later" is respected and it does not come back
    page = new_page(browser)
    page.goto(url, wait_until='domcontentloaded')
    page.wait_for_selector('#stage canvas')
    page.wait_for_timeout(1500)
    assert page.locator('#wizard').is_hidden()
    page.close()


def test_echo_of_her_own_voice_is_recognised(browser, url):
    page = new_page(browser)
    page.goto(url, wait_until='domcontentloaded')
    wait_until(page, "() => typeof window.isEcho === 'function'")
    r = page.evaluate("""() => {
        const out = [];
        out.push(isEcho('Я тебя слышу'));   // nothing was said yet
        lastSaid = {text: 'Привет! Я тебя слышу, как дела?', at: Date.now()};
        out.push(isEcho('я тебя слышу'));   // her own words coming back
        out.push(isEcho('нет, подожди, я хотел другое'));   // a different phrase: you
        out.push(isEcho('стоп'));   // too short to decide
        out.push(isEcho('Я тебя слышу', Date.now() + 10000));   // long after she stopped
        return out;
    }""")
    assert r == [False, True, False, False, False]
    page.close()


def test_page_works_under_the_strict_csp(browser, url):
    """No 'unsafe-inline' / 'unsafe-eval': the avatar must still be drawn, and the browser must report no policy violation."""
    page = new_page(browser)
    problems = []
    page.on('pageerror', lambda e: problems.append(str(e)))
    page.on('console', lambda m: problems.append(m.text) if m.type == 'error' and 'Content Security Policy' in m.text else None)
    page.goto(url, wait_until='domcontentloaded')
    page.wait_for_selector('#stage canvas')
    page.wait_for_selector('#loading', state='hidden')   # the model is loaded (no string evaluation here: the policy forbids it)
    assert not problems, problems
    page.close()


def test_page_loads_without_errors_and_answers(browser, url):
    page = new_page(browser)
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url, wait_until='domcontentloaded')
    page.wait_for_selector('#message', state='attached')
    page.wait_for_selector('#stage canvas')
    page.wait_for_timeout(1500)
    assert page.locator('#wizard').is_hidden()   # seen once already (the first test): it does not come back
    page.click('[data-tab=chat]')   # without a network the settings tab is the one open
    page.evaluate("document.getElementById('open-chat') && (document.getElementById('open-chat').click())")
    page.fill('#message', 'привет')
    page.click('#send')
    wait_until(page, "() => document.getElementById('log').innerText.includes('слышу')")
    assert not errors, errors
    page.close()
