"""How Luna sounds. Pure functions, no network and no imports from the rest of the project.

The speech service (edge-tts) accepts only three knobs per piece of speech: rate, pitch and volume, and the sentence text.
So the intonation is built from four things, and shape() combines them:
  1. her emotion on this line (the [happy] / [sad] ... tag the model wrote),
  2. her mood right now (valence and energy from character.py: a lively, glad Luna speaks brighter and faster),
  3. the time of day (late at night she is quieter and slower),
  4. the sentence itself: «!» lifts the voice, «?» rises, «...» slows and trails off, laughter («ха-ха-ха», «haha») and
     sighs («ах...», «эх...») get their own sound.
The user's own rate / pitch / volume settings from the page are added on top by the caller."""
import re

# emotion: (rate %, pitch Hz, volume %), relative to the user's own settings
PROSODY = {
    'neutral': (0, 0, 0), 'happy': (8, 10, 4), 'excited': (16, 18, 10), 'sad': (-18, -14, -14), 'angry': (10, -6, 16),
    'surprised': (6, 18, 8), 'shy': (-12, 6, -18), 'love': (-10, 8, -8), 'confused': (-6, 6, -4),
    'disgusted': (-4, -6, -2), 'scared': (12, 12, -8)}
LIMITS = {'rate': (-50, 50), 'pitch': (-50, 100), 'volume': (-40, 30)}

_TOKEN = r'(?:ха|хи|хе|хо|ha|hi|he)'
LAUGH_RE = re.compile(r'\b[аa]?(?:%s[-\s]?){2,7}' % _TOKEN, re.I)
LAUGH_TOKEN = re.compile(_TOKEN, re.I)
SIGH_RE = re.compile(r'^\s*(?:а+х+|э+х+|о+х+|у+ф+|sigh|ugh|phew|hmm+|х+м+)\b', re.I)
CLAMP = lambda kind, v: max(LIMITS[kind][0], min(LIMITS[kind][1], int(round(v))))


def laughter(text):
    """«Ха-ха-ха!» -> «Ха, ха, ха!»: the commas make the voice break the laugh into separate bursts instead of one word."""
    def burst(m):
        tokens = [t.lower() for t in LAUGH_TOKEN.findall(m.group(0))]
        tokens[0] = tokens[0].capitalize() if m.group(0)[:1].isupper() else tokens[0]
        return ', '.join(tokens) + ('' if text[m.end():m.end() + 1] in '!?.' else '!')
    return LAUGH_RE.sub(burst, text)


def laugh_share(text):
    """Which part of the words is laughter (0..1)."""
    words = re.findall(r'\w+', text)
    if not words:
        return 0.0
    laugh = sum(len(LAUGH_TOKEN.findall(m.group(0))) for m in LAUGH_RE.finditer(text))
    return min(1.0, laugh / len(words))


def shape(text, emotion='neutral', mood=None, hour=None):
    """-> {'text', 'rate', 'pitch', 'volume'} deltas for one line of speech (see the module docstring)."""
    rate, pitch, volume = PROSODY.get(emotion, PROSODY['neutral'])
    if mood:   # valence v in -1..1, energy e in 0..1
        rate += (mood['e'] - 0.5) * 12
        pitch += mood['v'] * 5
        volume += (mood['e'] - 0.5) * 8
    if hour is not None and (hour < 6 or hour >= 23):   # night: quiet and cozy
        rate -= 4
        volume -= 8
    body = text.strip()
    if laugh_share(body) > 0:
        share = laugh_share(body)
        body = laughter(body)
        pitch += 8 * share
        rate += 6 * share
    if SIGH_RE.search(body):
        rate -= 6
        pitch -= 4
    if body.endswith(('!', '！')):
        pitch += 4
        rate += 3
    elif body.endswith(('?', '？')):
        pitch += 3
    elif body.endswith(('...', '…', '‥')):
        rate -= 6
    return {'text': body, 'rate': CLAMP('rate', rate), 'pitch': CLAMP('pitch', pitch), 'volume': CLAMP('volume', volume)}
