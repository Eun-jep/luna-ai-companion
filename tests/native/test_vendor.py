"""The page uses the local copy of its libraries when it exists, the CDN otherwise; the files are served with the right types."""
import pytest

import app


def test_cdn_fallback_when_no_local_copy(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'VENDOR', tmp_path)
    html = app.with_libs('<script src="__LIB_PIXI__"></script><script src="__LIB_CUBISMCORE__"></script>')
    assert 'cdnjs.cloudflare.com' in html and 'cubism.live2d.com' in html and '__LIB_' not in html


def test_local_copy_wins(monkeypatch, tmp_path):
    (tmp_path / 'pixi.min.js').write_text('x')
    monkeypatch.setattr(app, 'VENDOR', tmp_path)
    html = app.with_libs('<script src="__LIB_PIXI__"></script><script src="__LIB_CUBISM4__"></script>')
    assert '/web/vendor/pixi.min.js' in html and 'cdn.jsdelivr.net' in html


def test_index_has_no_hard_cdn_script_tags():
    text = (app.ROOT / 'index.html').read_text(encoding='utf-8')
    assert '<script src="https://' not in text


def test_pins_cover_every_file():
    from tools import fetch_vendor
    assert set(fetch_vendor.FILES) == set(fetch_vendor.PINS)


def test_vision_tries_local_first():
    js = (app.ROOT / 'web' / 'vision.js').read_text(encoding='utf-8')
    assert js.index("'/web/vendor/mediapipe'") < js.index('base: MP_BASE')


@pytest.mark.skipif(not (app.ROOT / 'web' / 'vendor' / 'mediapipe' / 'vision_bundle.mjs').is_file(), reason='vendor files not downloaded')
def test_mjs_and_wasm_types():
    import mimetypes
    assert (app.ROOT / 'web' / 'vendor' / 'pixi.min.js').is_file()
    assert 'serve_file' in open(app.__file__, encoding='utf-8').read()
