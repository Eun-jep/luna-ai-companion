"""The reply as a script, and the pure text helpers around it (no state, no network): the stage directions the avatar may perform, which voice reads a
text, how a streamed reply is cut into sentences and code blocks, the steps of a plan. app.py imports everything from here."""
import re

from luna.core import faces
from luna.core.character import TAG_RE
from luna.hands.agent import ACT_RE

EMOTIONS = ['neutral', 'happy', 'sad', 'angry', 'surprised', 'shy', 'love', 'confused', 'excited', 'disgusted', 'scared']

GESTURES = ['nod', 'shake', 'tilt', 'wink', 'lean', 'shrug', 'bow', 'giggle', 'puff', 'blush', 'sigh', 'bounce']

LOOK_TARGETS = ['user', 'left', 'right', 'up', 'down', 'away']

# One multilingual neural voice reads every language; its character is shaped by pitch/rate in the UI.
TTS_VOICE = 'en-US-AvaMultilingualNeural'

JA_VOICE = 'ja-JP-NanamiNeural'   # reads only Japanese (and some Latin text); fails on Russian/Korean

FOREIGN_RE = re.compile('[Ѐ-ӿ가-힯ᄀ-ᇿ]')   # Cyrillic, Hangul

JA_RE = re.compile('[぀-ヿ一-鿿]')

NATIVE_VOICES = {'ru': 'ru-RU-SvetlanaNeural', 'ko': 'ko-KR-SunHiNeural', 'ja': JA_VOICE}   # "own voice of the language" option

HANGUL_RE = re.compile('[가-힯ᄀ-ᇿ]')

CYRILLIC_RE = re.compile('[Ѐ-ӿ]')

def pick_voice(text, native=False):
    """Nanami for Japanese speech, the multilingual voice for everything else.
    native=True: a native voice for text written in one non-English script (better stress and intonation)."""
    if native:
        if HANGUL_RE.search(text):
            return NATIVE_VOICES['ko']
        if CYRILLIC_RE.search(text) and not JA_RE.search(text):
            return NATIVE_VOICES['ru']
    return JA_VOICE if JA_RE.search(text) and not FOREIGN_RE.search(text) else TTS_VOICE

EMOJI_RE = re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]')

def tts_clean(text):
    """Text as it should be spoken: no emoji, markdown, links or leftover tags; pauses the voice understands."""
    text = TAG_RE.sub('', text)
    text = re.sub(r'https?://\S+', '', text)
    text = EMOJI_RE.sub('', text)
    text = re.sub(r'[*_#`~<>|^]+', '', text)
    text = text.replace('…', '...').replace(' — ', ', ').replace(' – ', ', ')
    text = re.sub(r'([!?])\1{2,}', r'\1', text)     # "!!!" -> "!"
    text = re.sub(r'\.{4,}', '...', text)
    text = re.sub(r'\s+', ' ', text).strip(' ,;:-')
    return text

VALID_TAGS = set(EMOTIONS) | set(GESTURES) | {'look:' + t for t in LOOK_TARGETS} | {'fx:' + n for n in faces.FX} | {'mo:' + n for n in faces.MOTIONS}

BOUNDARY_RE = re.compile(r'[.!?…]+[»"\')\]]*(?=\s)|[。！？]+|\n+')   # end of a sentence (not the dot of 3.5)

MIN_CHUNK = 12   # spoken characters: shorter pieces are joined to the next sentence

def split_ready(buffer):
    """Cut finished sentences off the front of the buffer -> (sentences, unfinished rest)."""
    pieces, pos = [], 0
    for match in BOUNDARY_RE.finditer(buffer):
        piece = buffer[pos:match.end()]
        if piece.count('[') > piece.count(']'):   # a command is still being written: do not cut inside it
            continue
        if len(TAG_RE.sub('', ACT_RE.sub('', piece)).strip()) >= MIN_CHUNK:
            pieces.append(piece.strip())
            pos = match.end()
    return pieces, buffer[pos:]

PLAN_MIN, PLAN_MAX, PLAN_STEP = 2, 6, 120

def parse_plan(arg):
    """The steps of [plan:a | b | c]: two to six short steps, or [] when it is not a usable plan."""
    steps = [' '.join(s.split()) for s in str(arg or '').split('|')]
    steps = [s for s in steps if len(s) >= 3]
    return [s[:PLAN_STEP] for s in steps[:PLAN_MAX]] if len(steps) >= PLAN_MIN else []

def parse_script(raw):
    """Model reply -> (script, spoken). The script keeps only known stage directions (the model
    may invent others); spoken is the same text with every direction removed."""
    script, spoken = clean_script(raw)
    return (script, spoken) if spoken else ('[neutral]', TAG_RE.sub('', raw).strip() or 'Хм.')

def clean_script(raw):
    def keep(match):
        tag = match.group(1).lower() + (':' + match.group(2).lower() if match.group(2) else '')
        return '[%s]' % tag if tag in VALID_TAGS else ''
    script = re.sub(r'[ \t]{2,}', ' ', TAG_RE.sub(keep, ACT_RE.sub('', raw))).strip()
    spoken = re.sub(r'[ \t]{2,}', ' ', TAG_RE.sub('', script)).strip()
    return script, spoken

MAX_MESSAGE, MAX_STORED = 12000, 3000   # a pasted file fits; the history keeps only the start of it

def pull_code(buffer, final=False):
    """Cut fenced code blocks out of the reply as it streams: ([('text', s) | ('code', {lang, text})], unfinished rest).
    Code is shown in the chat but never spoken."""
    segs = []
    while True:
        i = buffer.find('```')
        if i < 0:
            tail = len(buffer) - len(buffer.rstrip('`')) if not final else 0
            segs.append(('text', buffer[:len(buffer) - tail]))
            return segs, buffer[len(buffer) - tail:]
        j = buffer.find('```', i + 3)
        if j < 0 and not final:
            segs.append(('text', buffer[:i]))
            return segs, buffer[i:]
        body = buffer[i + 3:j if j >= 0 else len(buffer)]
        head, nl, rest = body.partition('\n')
        lang, code = (head.strip().lower(), rest) if nl and re.fullmatch(r'[\w+#.-]{0,20}', head.strip()) else ('', body)
        segs.append(('text', buffer[:i]))
        if code.strip():
            segs.append(('code', {'lang': lang, 'text': code.strip('\n')[:60000 if lang in ('lunadoc', 'lunaedit', 'lunaproject') else MAX_MESSAGE]}))
        buffer = buffer[j + 3:] if j >= 0 else ''
