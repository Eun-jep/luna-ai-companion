"""The updater (luna/core/updater.py): a feed on this computer, a package built here, a temp program folder. Nothing touches the real one."""
import hashlib
import http.server
import io
import json
import re
import threading
import zipfile
from pathlib import Path

import pytest

from luna import __version__, paths
from luna.core import updater

OLD = '0.9.0'
NEW = '9.9.9'


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def good_files(version=NEW):
    return {'luna/__init__.py': '__version__ = "%s"\n' % version, 'web/app.js': 'new js\n', 'luna/extra.py': 'X = 1\n'}


@pytest.fixture
def world(tmp_path, monkeypatch):
    root, data = tmp_path / 'program', tmp_path / 'data'
    (root / 'luna').mkdir(parents=True)
    (root / 'web').mkdir()
    (root / 'luna' / '__init__.py').write_text('__version__ = "%s"\n' % OLD, encoding='utf-8')
    (root / 'web' / 'app.js').write_text('old js\n', encoding='utf-8')
    (root / 'settings.json').write_text('{"mine": 1}', encoding='utf-8')
    data.mkdir()
    monkeypatch.setattr(paths, 'ROOT', root)
    monkeypatch.setattr(paths, 'DATA_DIR', data)
    monkeypatch.setattr(updater, 'current_version', lambda: OLD)
    updater._CHECKED.clear()
    served = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = served.get(self.path)
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%d' % srv.server_address[1]

    def publish(package, version=NEW, sha=None):
        served['/pkg.zip'] = package
        served['/feed.json'] = json.dumps({'version': version, 'url': 'pkg.zip', 'sha256': sha or hashlib.sha256(package).hexdigest(), 'notes': 'n'}).encode()
        return base + '/feed.json'

    yield root, publish
    srv.shutdown()
    srv.server_close()


def code_of(fn, *a):
    with pytest.raises(updater.UpdateError) as e:
        fn(*a)
    return str(e.value)


def test_version_matches_pyproject():
    toml = (Path(__file__).resolve().parents[2] / 'pyproject.toml').read_text(encoding='utf-8')
    assert re.search(r'^version = "%s"' % re.escape(__version__), toml, re.M)


def test_install_replaces_program_files_and_keeps_user_files(world):
    root, publish = world
    feed = publish(make_zip(good_files()))
    r = updater.check(feed)
    assert r['available'] and r['version'] == NEW
    out = updater.install()
    assert out['version'] == NEW and out['restart']
    assert (root / 'web' / 'app.js').read_text() == 'new js\n' and (root / 'luna' / 'extra.py').exists()
    assert (root / 'settings.json').read_text() == '{"mine": 1}'
    assert updater.has_backup()


def test_rollback_restores_and_removes_added_files(world):
    root, publish = world
    updater.check(publish(make_zip(good_files())))
    updater.install()
    assert updater.rollback()['version'] == OLD
    assert (root / 'web' / 'app.js').read_text() == 'old js\n'
    assert not (root / 'luna' / 'extra.py').exists()
    assert (root / 'luna' / '__init__.py').read_text().strip() == '__version__ = "%s"' % OLD
    assert code_of(updater.rollback) == 'nothing'


def test_same_or_older_version_is_not_offered(world):
    _, publish = world
    r = updater.check(publish(make_zip(good_files(OLD)), version=OLD))
    assert not r['available']
    assert code_of(updater.install) == 'nothing'


def test_hash_mismatch_installs_nothing(world):
    root, publish = world
    updater.check(publish(make_zip(good_files()), sha='0' * 64))
    assert code_of(updater.install) == 'hash'
    assert (root / 'web' / 'app.js').read_text() == 'old js\n'


def test_relabelled_version_is_refused(world):
    root, publish = world
    updater.check(publish(make_zip(good_files('0.8.0')), version=NEW))
    assert code_of(updater.install) == 'version'
    assert (root / 'web' / 'app.js').read_text() == 'old js\n'


@pytest.mark.parametrize('name', ['../evil.py', 'luna/../../evil.py', '/abs.py', 'C:/win.py', 'web\\..\\..\\x.js', 'settings.json', 'actions.json',
                                  'web/vendor/lib.js', 'desktop/node_modules/x.js', 'other/file.txt', 'luna/trailing. '])
def test_unsafe_paths_are_refused(world, name):
    root, publish = world
    files = good_files()
    files[name] = 'x'
    updater.check(publish(make_zip(files)))
    assert code_of(updater.install) == 'unsafe'
    assert (root / 'web' / 'app.js').read_text() == 'old js\n' and not (root.parent / 'evil.py').exists()


def test_syntax_error_in_package_installs_nothing(world):
    root, publish = world
    files = good_files()
    files['luna/broken.py'] = 'def (:\n'
    updater.check(publish(make_zip(files)))
    assert code_of(updater.install) == 'syntax'
    assert (root / 'web' / 'app.js').read_text() == 'old js\n'


def test_failure_half_way_restores_everything(world, monkeypatch):
    root, publish = world
    updater.check(publish(make_zip(good_files())))
    real, calls = updater.os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError('disk full')
        return real(src, dst)

    monkeypatch.setattr(updater.os, 'replace', flaky)
    assert code_of(updater.install) == 'write'
    monkeypatch.undo()
    assert (root / 'web' / 'app.js').read_text() == 'old js\n'
    assert (root / 'luna' / '__init__.py').read_text().strip() == '__version__ = "%s"' % OLD
    assert not (root / 'luna' / 'extra.py').exists()


def test_not_a_zip_and_bad_feed(world):
    _, publish = world
    updater.check(publish(b'not a zip'))
    assert code_of(updater.install) == 'bad'
    with pytest.raises(updater.UpdateError):
        updater.check('http://127.0.0.1:1/none.json')


@pytest.mark.parametrize('url', ['http://example.com/feed.json', 'ftp://x/y', 'file:///etc/passwd', 'javascript:1', ''])
def test_only_https_or_loopback(url):
    assert not updater.url_ok(url)
    assert code_of(updater.check, url or None) in ('feed', 'nofeed')


def test_https_and_loopback_are_fine():
    assert updater.url_ok('https://example.com/f.json') and updater.url_ok('http://127.0.0.1:5/f') and updater.url_ok('http://localhost/f')


def test_nothing_checked_means_nothing_installed(world):
    assert code_of(updater.install) == 'nothing'


def test_checked_offer_expires(world, monkeypatch):
    _, publish = world
    updater.check(publish(make_zip(good_files())))
    updater._CHECKED['at'] -= updater.TTL + 5
    assert code_of(updater.install) == 'nothing'


def test_bad_manifest_values(world):
    _, publish = world
    feed = publish(make_zip(good_files()), version='1.x')
    assert code_of(updater.check, feed) == 'bad'
    feed = publish(make_zip(good_files()), sha='zz')
    assert code_of(updater.check, feed) == 'bad'
