"""Local speech (luna/senses/localtts.py): the choice of voice is tested everywhere; the real Windows voice only where one is installed."""
import os

import pytest

from luna.senses import localtts

VOICES = [{'name': 'Microsoft Irina Desktop', 'culture': 'ru-RU'}, {'name': 'Microsoft Zira Desktop', 'culture': 'en-US'},
          {'name': 'Microsoft Haruka Desktop', 'culture': 'ja-JP'}]


@pytest.mark.parametrize('text, lang', [('Привет, как дела?', 'ru'), ('Hello there', 'en'), ('こんにちは', 'ja'), ('안녕하세요', 'ko'), ('12345', 'en')])
def test_language_of(text, lang):
    assert localtts.language_of(text) == lang


def test_pick_matches_language_or_none():
    assert localtts.pick('Привет', VOICES) == 'Microsoft Irina Desktop'
    assert localtts.pick('Hello', VOICES) == 'Microsoft Zira Desktop'
    assert localtts.pick('こんにちは', VOICES) == 'Microsoft Haruka Desktop'
    assert localtts.pick('안녕하세요', VOICES) is None   # no Korean voice: better silence than Korean read in an English voice


def test_rate_mapping_is_clamped():
    assert [localtts.sapi_rate(x) for x in (0, 10, -10, 50, -50, 400, -400)] == [0, 1, -1, 5, -5, 10, -10]


def test_no_voice_for_language_raises():
    if os.name != 'nt':
        pytest.skip('Windows only')
    with pytest.raises(localtts.LocalVoiceError) as e:
        localtts.synthesize('안녕하세요', available=VOICES)
    assert str(e.value) == 'novoice'


def test_text_cannot_become_a_command(monkeypatch):
    """The text reaches PowerShell only as a file and environment variables, never inside the command."""
    if os.name != 'nt':
        pytest.skip('Windows only')
    seen = {}

    def fake(script, env=None, timeout=0):
        seen.update(script=script, env=env)
        open(env['LUNA_OUT'], 'wb').write(b'RIFFxxxx')
        assert open(env['LUNA_IN'], encoding='utf-8').read() == evil
        return ''
    evil = 'Hello"; Remove-Item C:\\ -Recurse; "'
    monkeypatch.setattr(localtts, '_powershell', fake)
    assert localtts.synthesize(evil, available=VOICES) == b'RIFFxxxx'
    assert 'Remove-Item' not in seen['script'] and evil not in ' '.join(seen['env'].values()) and seen['env']['LUNA_VOICE'] == 'Microsoft Zira Desktop'


@pytest.mark.slow
def test_real_windows_voice_speaks():
    have = localtts.voices()
    if not have:
        pytest.skip('no Windows speech voices here')
    sample = {'ru': 'Привет, это проверка.', 'en': 'Hello, this is a test.', 'ja': 'こんにちは。'}
    lang = next(c[:2] for c in (v['culture'].lower() for v in have) if c[:2] in sample)
    audio = localtts.synthesize(sample[lang], available=have)
    assert audio[:4] == b'RIFF' and len(audio) > 2000


# ---- the choice of engine in app.speak ----

def _app(monkeypatch, edge):
    import app
    monkeypatch.setattr(app, 'synthesize', edge)
    monkeypatch.setattr(app.localtts, 'synthesize', lambda text, rate=0, volume=0, available=None: b'RIFFlocal')
    return app


def _edge_ok(*a, **k):
    return b'mp3'


def _edge_down(*a, **k):
    raise OSError('no network')


def test_cloud_engine_uses_cloud_and_does_not_fall_back(monkeypatch):
    app = _app(monkeypatch, _edge_ok)
    assert app.speak('Hello', False, 0, 0, 0, 'edge') == (b'mp3', 'audio/mpeg')
    app = _app(monkeypatch, _edge_down)
    with pytest.raises(OSError):
        app.speak('Hello', False, 0, 0, 0, 'edge')


def test_auto_falls_back_to_windows_voice_when_cloud_fails(monkeypatch):
    app = _app(monkeypatch, _edge_down)
    assert app.speak('Hello', False, 0, 0, 0, 'auto') == (b'RIFFlocal', 'audio/wav')
    app = _app(monkeypatch, lambda *a, **k: b'')
    assert app.speak('Hello', False, 0, 0, 0, 'auto')[1] == 'audio/wav'


def test_local_engine_never_touches_the_cloud(monkeypatch):
    def boom(*a, **k):
        raise AssertionError('the cloud voice was called')
    app = _app(monkeypatch, boom)
    assert app.speak('Привет', True, 0, 0, 0, 'local') == (b'RIFFlocal', 'audio/wav')
