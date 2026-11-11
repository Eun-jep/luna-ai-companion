"""Her voice as a set of recordings: several minutes of her ordinary speaking voice (the same edge-tts voice as in conversation),
saved in studio/reference/. The song studio matches every sung sound to the closest sound in these recordings, which is what gives
the covers her timbre without training anything.

Run with the project's Python:  py studio/make_reference.py [voice] [pitch Hz] [rate %]  (needs internet, takes a few minutes, once).
By default it records her voice as she speaks in conversation: the multilingual voice with pitch +65 Hz (the page's default pitch).
Set the same pitch and rate as in the page's voice settings; old recordings in studio/reference/ are kept, so delete them first when changing."""
import asyncio
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'reference'
ROOT = HERE.parent
MAX_MINUTES = 9          # seconds of speech are estimated from the text length; enough variety for every vowel and consonant
CHARS_PER_SECOND = 14


def sentences():
    """Plain Russian sentences from the project's own texts: every sound of the language, no private data."""
    text = (ROOT / 'README.txt').read_text(encoding='utf-8', errors='replace')
    out = []
    for raw in re.split(r'[\r\n]+|(?<=[.!?])\s+', text):
        s = re.sub(r'\s+', ' ', raw).strip(' -•*#')
        if 25 <= len(s) <= 140 and re.search('[а-яё]{4}', s, re.I) and not re.search(r'[A-Za-z]{4}|[\\/_=<>{}\[\]:@]', s):
            out.append(s)
    seen, unique = set(), []
    for s in out:
        if s.lower() not in seen:
            seen.add(s.lower())
            unique.append(s)
    return unique


async def main():
    import edge_tts
    voice = sys.argv[1] if len(sys.argv) > 1 else 'en-US-AvaMultilingualNeural'
    pitch = int(sys.argv[2]) if len(sys.argv) > 2 else 65
    rate = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    global PITCH, RATE
    PITCH, RATE = '%+dHz' % pitch, '%+d%%' % rate
    OUT.mkdir(exist_ok=True)
    budget, n = MAX_MINUTES * 60 * CHARS_PER_SECOND, 0
    chunk, size, batch = [], 0, 0
    for s in sentences():
        chunk.append(s)
        size += len(s)
        if size >= 900:
            await save(edge_tts, voice, ' '.join(chunk), OUT / ('ref%03d.mp3' % batch))
            budget -= size
            chunk, size, batch = [], 0, batch + 1
            print('saved', batch, flush=True)
            if budget <= 0:
                break
    if chunk and budget > 0:
        await save(edge_tts, voice, ' '.join(chunk), OUT / ('ref%03d.mp3' % batch))
    print('done: %d files in %s' % (len(list(OUT.glob('*.mp3'))), OUT))


PITCH, RATE = '+65Hz', '+0%'


async def save(edge_tts, voice, text, path):
    if path.exists():
        return
    await edge_tts.Communicate(text, voice, rate=RATE, pitch=PITCH).save(str(path))


if __name__ == '__main__':
    asyncio.run(main())
