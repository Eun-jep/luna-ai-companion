"""Which song is playing, by its sound.

A digital fingerprint of a few seconds of sound is made on this computer (shazamio-core) and only that fingerprint, never the sound
itself, is sent to the Shazam service, which answers with a title and an artist. It happens only when the person has switched it on
(a setting, off by default) and asks "what song is this". The answer is a guess by an outside service: the caller treats the title as
data and says it may be wrong.

No imports from the rest of the project. identify() is replaceable (tests use a fake)."""
import asyncio
import importlib.util
import io
import re
import threading
import wave

import numpy as np

SR = 16000
ERROR = ''          # why the last attempt failed (for the log)


def available():
    return importlib.util.find_spec('shazamio') is not None


def wav_bytes(audio, sr=SR):
    """Mono 16-bit WAV in memory (nothing is written to disk)."""
    pcm = (np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def clean(text, limit=80):
    """A title from an outside service is data: no brackets or quotes that could look like a tag, and a limited length."""
    return ' '.join(re.sub(r'[\[\]<>{}"«»`\\]', ' ', str(text or '')).split())[:limit]


def parse(answer):
    """The Shazam answer -> {'title', 'artist'}, or None when nothing matched."""
    track = (answer or {}).get('track') if isinstance(answer, dict) else None
    if not isinstance(track, dict):
        return None
    title, artist = clean(track.get('title')), clean(track.get('subtitle'))
    return {'title': title, 'artist': artist} if title else None


def identify(audio, timeout=25):
    """About 8-12 seconds of audio (16 kHz mono floats) -> {'title', 'artist'} or None (no match, no package, no network)."""
    global ERROR
    ERROR = ''
    if not available() or audio is None or len(audio) < SR * 4:
        return None
    out = {}

    def run():
        try:
            from shazamio import Shazam

            async def go():
                shazam = Shazam()
                try:
                    return await asyncio.wait_for(shazam.recognize(wav_bytes(audio)), timeout)
                finally:
                    for name in ('http_client', 'client'):          # the connection is closed, or the library complains at exit
                        closer = getattr(getattr(shazam, name, None), 'close', None)
                        if closer:
                            try:
                                res = closer()
                                if asyncio.iscoroutine(res):
                                    await res
                            except Exception:
                                pass
            out['answer'] = asyncio.run(go())
        except BaseException as exc:                      # any failure is simply "not recognized"
            out['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:120])
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout + 5)
    if 'answer' not in out:
        ERROR = out.get('error', 'timeout')
        return None
    return parse(out['answer'])
