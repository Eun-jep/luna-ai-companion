"""What Luna hears from the computer's speakers: a short listen now and then, understood on this machine.

Only the sound that goes OUT of the speakers (WASAPI loopback) is captured, never the microphone. A few seconds are recorded
into memory, turned into a short description (speech with its words, or music with its character) and thrown away: no audio
file is ever written, and the recognition model runs locally (Vosk), so the sound itself never leaves the computer.
Only the short text description may later be given to the chosen AI when she comments on what is playing.

No imports from the rest of the project. The capture and recognition functions are replaceable (tests use fakes)."""
from luna import paths
import importlib.util
import json
import os
import re
import threading
import time
from pathlib import Path

try:
    import numpy as np
except ImportError:   # hearing is then simply off (available() says so); luna/core/deps.py tells him what to install
    np = None

SR = 16000
SECONDS = 7                 # one listen
QUIET = 0.0015              # rms below this is silence (a loopback with nothing playing is exactly 0)
MODEL_DIR = paths.ROOT / 'models' / 'vosk'
MODELS = {'ru': ('vosk-model-small-ru-0.22', 'https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip'),
          'en': ('vosk-model-small-en-us-0.15', 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip'),
          'ko': ('vosk-model-small-ko-0.22', 'https://alphacephei.com/vosk/models/vosk-model-small-ko-0.22.zip'),
          'ja': ('vosk-model-small-ja-0.22', 'https://alphacephei.com/vosk/models/vosk-model-small-ja-0.22.zip')}
# Korean and Japanese go through SenseVoice (sherpa-onnx): the small Vosk models for them hear real voices poorly.
SENSE_DIR = paths.ROOT / 'models' / 'sherpa'
SENSE_NAME = 'sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17'
SENSE_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/' + SENSE_NAME + '.tar.bz2'
SENSE_LANGS = ('ko', 'ja')
# Russian speech to the microphone goes through GigaAM (sherpa-onnx, about 170 MB, downloaded once), English through SenseVoice (the same
# model as for Korean and Japanese): the small Vosk model beside them keeps showing rough live words and stays the recognizer for the
# sound from the speakers.
EXACT_LANGS = ('ru', 'en')
GIGA_NAME = 'sherpa-onnx-nemo-ctc-giga-am-v2-russian-2025-04-19'
GIGA_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/' + GIGA_NAME + '.tar.bz2'
MAX_TEXT = 300
FRESH = 90                  # a result older than this many seconds is not "now"
PRIVATE = ('zoom', 'teams', 'skype', 'discord', 'telegram', 'whatsapp', 'google meet', 'meet.google', 'webex', 'slack', 'viber',
           'звонок', 'созвон', 'видеозвонок', 'конференц')

_lock = threading.Lock()
_state = {'status': 'idle', 'error': ''}    # idle | loading | ready | error
_model = None
_draft = None               # a small Vosk model beside SenseVoice (ko, ja): rough words shown live while the sentence is spoken
_exact = None               # the more exact microphone recognizer for ru / en (None until it is loaded, or when it cannot be)
_lang = ''
_mute_until = 0.0
LAST = {'t': 0.0, 'kind': 'silence', 'text': '', 'about': ''}


def available():
    """Which of the two pieces are installed: the loopback capture and the recognizer."""
    return {'capture': np is not None and importlib.util.find_spec('soundcard') is not None,
            'asr': np is not None and importlib.util.find_spec('vosk') is not None}


def is_private(title):
    """Calls and messengers: their sound is somebody else's conversation, so she does not listen at all."""
    low = ' '.join(str(title or '').lower().split())
    return any(word in low for word in PRIVATE)


def mute(seconds):
    """Her own voice is about to play through the speakers: do not mistake it for something she heard."""
    global _mute_until
    _mute_until = max(_mute_until, time.time() + seconds)


def muted(now=None):
    return (now or time.time()) < _mute_until


# ---- her own voice coming back through the microphone (speakers near the mic): it is not him, and she must not answer herself ----
ECHO_FOR = 120          # seconds a line she spoke can still come back as an echo
ECHO_SHARE = 0.7        # this share of the heard words (or letter pairs) found in her recent lines = it was her
ECHO_MIN = 3            # fewer words than this can be anyone's: "да", "хорошо", "okay"
_said = []              # [(time, set of tokens)] of her last spoken lines, in memory only


def _tokens(text):
    low = str(text or '').lower()
    cjk = re.findall(r'[぀-ヿ一-鿿가-힯]+', low)
    if cjk:       # no spaces between words: pairs of neighbouring letters stand in for words
        return {run[i:i + 2] for run in cjk for i in range(max(1, len(run) - 1))}
    return {w for w in re.findall(r'\w{2,}', low)}


def said(text, now=None):
    """Called when her line goes to the speakers: remembered for a couple of minutes, to tell an echo from him."""
    now = now or time.time()
    _said[:] = [(t, tok) for t, tok in _said if now - t < ECHO_FOR][-7:]
    tok = _tokens(text)
    if tok:
        _said.append((now, tok))


def echo_of_her(text, now=None):
    """True when the heard words are (almost) all words she herself just said: her voice from the speakers, not him."""
    now = now or time.time()
    heard = _tokens(text)
    cjk = bool(re.search(r'[぀-ヿ一-鿿가-힯]', str(text or '')))
    if len(heard) < (ECHO_MIN if not cjk else ECHO_MIN + 2):
        return False
    mine = set().union(*[tok for t, tok in _said if now - t < ECHO_FOR]) if _said else set()
    return bool(mine) and len(heard & mine) / len(heard) >= ECHO_SHARE


# ---- the sound itself ----

def _com():
    """soundcard talks to Windows audio through COM, which every thread (the server answers on its own threads) must join first."""
    if os.name == 'nt':
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)


def _loopbacks():
    """Every output the computer has (speakers, headphones, a virtual cable): the player may use any of them, not only the default one."""
    import soundcard as sc
    _com()
    default = str(sc.default_speaker().name)
    mics = [m for m in sc.all_microphones(include_loopback=True) if getattr(m, 'isloopback', False)]
    mics.sort(key=lambda m: str(m.name) != default)        # the default one first
    return mics[:4]


def _record(mic, seconds, out, i):
    try:
        import warnings
        _com()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')                 # "data discontinuity" on a busy computer: the sound is still there
            with mic.recorder(samplerate=SR, channels=1) as rec:
                out[i] = np.asarray(rec.record(numframes=SR * seconds), dtype=np.float32).reshape(-1)
    except Exception as exc:
        out[i] = exc


def _capture(seconds=SECONDS):
    """Mono float32 at 16 kHz from the speakers' loopback: all outputs at once, the one with the loudest sound wins."""
    mics = _loopbacks()
    out = [None] * len(mics)
    threads = [threading.Thread(target=_record, args=(m, seconds, out, i), daemon=True) for i, m in enumerate(mics)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(seconds + 15)
    got = [a for a in out if isinstance(a, np.ndarray) and a.size]
    if not got:
        errors = [a for a in out if isinstance(a, Exception)]
        raise errors[0] if errors else RuntimeError('no output device')
    return max(got, key=lambda a: float(np.abs(a).max()))


def _lift(audio):
    """A quiet recording is raised to a level the recognizer can use (peak 0.5); the sound's own loudness is judged before this."""
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    return audio * min(30.0, 0.5 / peak) if 0 < peak < 0.3 else audio


VOSK_HOST = 'https://alphacephei.com/vosk/models/'


def _download(url, dest, hosts=(VOSK_HOST,), limit=200 << 20):
    """A file from one of the few allowed addresses (https only) into dest, at most `limit` bytes."""
    import urllib.request
    if not url.startswith(tuple(hosts)):
        raise ValueError('model url')
    got = 0
    with urllib.request.urlopen(url, timeout=60) as resp, open(dest, 'wb') as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            got += len(chunk)
            if got > limit:
                raise ValueError('model too large')
            out.write(chunk)


def _unpack(archive, folder):
    """Extract a zip without letting any entry escape the folder."""
    import zipfile
    folder = Path(folder).resolve()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target = (folder / info.filename).resolve()
            if folder != target and folder not in target.parents:
                raise ValueError('unsafe archive')
        z.extractall(folder)


def _sense_ready():
    """SenseVoice is used when its package is installed; the model (about 160 MB) is downloaded the first time."""
    return importlib.util.find_spec('sherpa_onnx') is not None


def _fetch_sherpa(name, url):
    """The model folder models/sherpa/<name>, downloaded from the official sherpa-onnx releases the first time."""
    path = SENSE_DIR / name
    if not (path / 'model.int8.onnx').is_file():
        import tarfile
        SENSE_DIR.mkdir(parents=True, exist_ok=True)
        archive = SENSE_DIR / (name + '.tar.bz2')
        _download(url, archive, hosts=('https://github.com/k2-fsa/sherpa-onnx/releases/',), limit=400 << 20)
        with tarfile.open(archive) as t:
            folder = SENSE_DIR.resolve()
            for m in t.getmembers():
                target = (folder / m.name).resolve()
                if not (m.isfile() or m.isdir()) or (folder != target and folder not in target.parents):
                    raise ValueError('unsafe archive')
            t.extractall(folder)
        archive.unlink()
    return path


def _load_sense(lang):
    import sherpa_onnx
    path = _fetch_sherpa(SENSE_NAME, SENSE_URL)
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(path / 'model.int8.onnx'), tokens=str(path / 'tokens.txt'), language=lang, use_itn=True, num_threads=2)


def _load_exact(lang):
    import sherpa_onnx
    if lang == 'en':
        return _load_sense('en')
    path = _fetch_sherpa(GIGA_NAME, GIGA_URL)
    return sherpa_onnx.OfflineRecognizer.from_nemo_ctc(model=str(path / 'model.int8.onnx'), tokens=str(path / 'tokens.txt'), num_threads=2)


def prepare(lang='ru'):
    """Make sure the recognizer for this language is there (the first time it is downloaded, about 45 MB) and loaded, in the
    background. state() tells how it went."""
    lang = lang if lang in MODELS else 'en'

    def vosk_model():
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)
        name, url = MODELS[lang]
        path = MODEL_DIR / name
        if not path.is_dir():
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            archive = MODEL_DIR / (name + '.zip')
            _download(url, archive)
            _unpack(archive, MODEL_DIR)
            archive.unlink()
        return Model(str(path))

    def load():
        global _model, _lang, _draft, _exact
        try:
            if lang in SENSE_LANGS and _sense_ready():
                _model, _lang, _draft, _exact = _load_sense(lang), lang, None, None
                _state.update(status='ready', error='')
                try:                                  # the live draft is a bonus: without it the sentence just appears after the pause
                    _draft = vosk_model()
                except Exception:
                    _draft = None
                return
            _model, _lang, _draft, _exact = vosk_model(), lang, None, None
            _state.update(status='ready', error='')
            if lang in EXACT_LANGS and _sense_ready():   # the exact recognizer is a bonus: until it is there (or without it) Vosk listens
                try:
                    _exact = _load_exact(lang)
                except Exception:
                    _exact = None
        except Exception as exc:
            _state.update(status='error', error='%s: %s' % (type(exc).__name__, str(exc)[:160]))
    with _lock:
        if _state['status'] == 'loading' or (_state['status'] == 'ready' and _lang == lang):
            return
        _state.update(status='loading', error='')
    threading.Thread(target=load, daemon=True).start()


def state():
    return dict(_state, lang=_lang, **available())


def _asr(audio):
    """-> (text, share of 'no speech', average confidence mapped to a log-probability-like number)."""
    if hasattr(_model, 'create_stream'):    # SenseVoice (no word confidences)
        stream = _model.create_stream()
        stream.accept_waveform(SR, np.asarray(audio, dtype=np.float32))
        _model.decode_stream(stream)
        text = re.sub(r'<\|[^|]*\|>', '', stream.result.text).strip()
        return (text, 0.4, -0.6) if text else ('', 1.0, -9.0)
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(_model, SR)
    rec.SetWords(True)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    for i in range(0, len(pcm), 8000):
        rec.AcceptWaveform(pcm[i:i + 8000])
    result = json.loads(rec.FinalResult())
    text = (result.get('text') or '').strip()
    words = result.get('result') or []
    if not text or not words:
        return '', 1.0, -9.0
    conf = sum(w.get('conf', 0.0) for w in words) / len(words)
    return text, 1.0 - conf, conf - 1.0


# ---- understanding it (pure) ----

def features(audio):
    """rms level, brightness (0..1) and how much the loudness moves, from the samples alone."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size < 1024:
        return {'rms': 0.0, 'bright': 0.0, 'pulse': 0.0}
    rms = float(np.sqrt(np.mean(audio ** 2)))
    spectrum = np.abs(np.fft.rfft(audio[:SR * 4] if audio.size > SR * 4 else audio))
    freqs = np.fft.rfftfreq(min(audio.size, SR * 4), 1.0 / SR)
    centroid = float((spectrum * freqs).sum() / (spectrum.sum() + 1e-9))
    frames = audio[:audio.size // 800 * 800].reshape(-1, 800)
    level = np.sqrt((frames ** 2).mean(axis=1))
    pulse = float(level.std() / (level.mean() + 1e-9))
    return {'rms': rms, 'bright': min(1.0, centroid / 4000.0), 'pulse': min(1.0, pulse)}


def character(f):
    """Words for how a piece of music feels: 'quiet and calm', 'loud and driving'..."""
    loud = 'громкая' if f['rms'] > 0.08 else 'тихая' if f['rms'] < 0.02 else 'средней громкости'
    feel = 'яркая, бодрая' if f['bright'] > 0.55 else 'тёплая, глубокая' if f['bright'] < 0.3 else 'ровная'
    drive = 'с резким, ритмичным пульсом' if f['pulse'] > 0.6 else 'плавная'
    return '%s, %s, %s' % (loud, feel, drive)


def count_words(text):
    """Words in recognized text. Japanese has no spaces: a run of kana/kanji counts about one word per 2.5 letters, otherwise a whole
    Japanese sentence would be one word (heard speech taken for music, and a pace that means nothing)."""
    total = 0
    for token in str(text or '').split():
        total += max(1, round(len(token) / 2.5)) if re.search(r'[぀-ヿ一-鿿]', token) else 1
    return total


def classify(audio, asr=None):
    """-> {'kind': 'silence'|'voice'|'music', 'text', 'about'}.
    voice = words are heard (a talk, a film, a song with lyrics), music = sound without understandable words."""
    f = features(audio)
    if f['rms'] < QUIET:
        return {'kind': 'silence', 'text': '', 'about': ''}
    text, no_speech, logprob = asr if asr else ('', 1.0, -9.0)
    words = count_words(text)
    if words >= 4 and no_speech < 0.6 and logprob > -0.6:
        return {'kind': 'voice', 'text': text[:MAX_TEXT], 'about': 'слышны слова: «%s»' % text[:MAX_TEXT]}
    return {'kind': 'music', 'text': '', 'about': 'играет музыка (%s)' % character(f)}


_kept = None                # the sound of the last listen, held in memory only when asked (for the song fingerprint), taken once


def take_audio():
    """The sound kept by listen(keep=True), once; it is forgotten at once."""
    global _kept
    audio, _kept = _kept, None
    return audio


def listen(lang='ru', keep=False, seconds=SECONDS):
    """Record a few seconds and describe them. Returns the result (also kept as LAST), or None when it must not count:
    her own voice was playing, no recognizer yet, or nothing could be recorded. keep=True: the sound stays in memory until take_audio()."""
    global LAST, _kept
    _kept = None
    if muted() or _state['status'] != 'ready' or _lang != (lang if lang in MODELS else 'en'):
        return None
    t0 = time.time()
    try:
        audio = _capture(seconds)
        asr = _asr(_lift(audio)) if features(audio)['rms'] >= QUIET else None
    except Exception as exc:
        _state['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:160])
        return None
    if muted() or _mute_until > t0:     # she started speaking while we listened: that was her
        return None
    LAST = dict(classify(audio, asr), t=time.time())
    if keep and LAST['kind'] != 'silence':
        _kept = audio
    return LAST


def fresh(now=None):
    """What she heard a moment ago, or None."""
    now = now or time.time()
    if LAST['kind'] == 'silence' or now - LAST['t'] > FRESH:
        return None
    return LAST


def reset():
    global LAST, _mute_until
    LAST = {'t': 0.0, 'kind': 'silence', 'text': '', 'about': ''}
    _mute_until = 0.0


# ---- the microphone: speaking to her, recognized on this computer (the browser engine fails inside Electron) ----

_cancel = threading.Event()
MIC_MAX = 14.0              # longest single utterance, seconds
MIC_WAIT = 7.0              # how long to wait for the first word
MIC_STEP = SR // 10         # the microphone is read and recognized in tenths of a second, while she is still talking
_partial = ''               # the words recognized so far in the current utterance (the page shows them at once)


def cancel_mic():
    _cancel.set()


class _Mic:
    """The microphone through PortAudio: a callback keeps filling a queue, so no sound is lost while the recognizer is busy
    (reading it block by block with soundcard dropped pieces of speech: "data discontinuity", and the words came out wrong)."""
    def __init__(self):
        import queue
        import sounddevice as sd
        self.q = queue.Queue()
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype='float32', blocksize=MIC_STEP, callback=self._fill)

    def _fill(self, data, frames, info, status):
        self.q.put(data[:, 0].copy())

    def __enter__(self):
        self.stream.start()
        return self

    def __exit__(self, *exc):
        self.stream.stop()
        self.stream.close()

    def record(self, numframes):
        return self.q.get(timeout=3)


def _open_mic():
    if importlib.util.find_spec('sounddevice'):
        return _Mic()
    import soundcard as sc
    _com()
    return sc.default_microphone().recorder(samplerate=SR, channels=1)


class Agc:
    """Raises a quiet microphone to a level the recognizer can use (it hears nothing at all from a very quiet signal): the gain
    follows the loudest recent sound, never amplifies the room's own noise to speech level, and drops at once when it gets loud."""
    TARGET, LIMIT, DECAY = 0.3, 40.0, 0.97

    def __init__(self):
        self.peak, self.gain, self.seen, self.noise = 0.0, 1.0, 0, 0.0

    def __call__(self, chunk):
        level = float(np.abs(chunk).max()) if chunk.size else 0.0
        if self.seen < 3:   # the first moments are the room: they set the noise floor
            self.noise = max(self.noise, level)
            self.seen += 1
        self.peak = max(self.peak * self.DECAY, level)
        want = min(self.LIMIT, self.TARGET / max(self.peak, self.noise * 3.0, 0.01))
        self.gain = want if want < self.gain else self.gain + (want - self.gain) * 0.25
        return np.clip(chunk * max(1.0, self.gain), -1.0, 1.0)


def mic_partial():
    return _partial


_level = {'peak': 0.0, 'gain': 1.0}     # what the microphone gives (before the automatic gain) and the gain applied; for the microphone test


def mic_level():
    return dict(_level)


def _new_stream():
    """A streaming recognizer: audio goes in as it is recorded; the recognizer itself finds where the sentence ends."""
    if _lang in EXACT_LANGS and _exact is not None:
        return SenseStream(_exact, _model)
    if _lang in SENSE_LANGS and not hasattr(_model, 'AcceptWaveform') and hasattr(_model, 'create_stream'):
        return SenseStream(_model, _draft)
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(_model, SR)

    class Stream:
        def feed(self, pcm): return rec.AcceptWaveform(pcm)
        def partial(self): return (json.loads(rec.PartialResult()).get('partial') or '').strip()
        def result(self): return (json.loads(rec.Result()).get('text') or '').strip()
        def final(self): return (json.loads(rec.FinalResult()).get('text') or '').strip()
    return Stream()


class SenseStream:
    """The same few members as the Vosk stream, over an offline recognizer: a simple loudness gate finds where speech starts
    and ends, and the sentence is recognized once, when it is over. (Recognizing the growing sentence again and again, to show
    words live, is too heavy for a weak processor: one pass takes about as long as the speech itself.)"""
    REDO = 0.0              # seconds of new speech between two looks at the partial text; 0 = no partial text
    PAUSE = 0.7             # this much quiet after speech ends the sentence

    def __init__(self, recognizer, draft=None):
        self.rec, self.buf, self.noise, self.quiet, self.since, self.text, self.spoke = recognizer, [], 0.01, 0.0, 0.0, '', False
        self.live = None
        if draft is not None:                         # cheap rough words while speaking; the sentence itself comes from SenseVoice
            from vosk import KaldiRecognizer
            self.live = KaldiRecognizer(draft, SR)

    def _rough(self):
        try:
            if not self.live:
                return ''
            text = (json.loads(self.live.PartialResult()).get('partial') or '').strip()
            return text.replace(' ', '') if _lang == 'ja' else text      # Japanese is written without spaces
        except Exception:
            return ''

    def _decode(self):
        if not self.buf:
            return ''
        stream = self.rec.create_stream()
        stream.accept_waveform(SR, np.concatenate(self.buf))
        self.rec.decode_stream(stream)
        return re.sub(r'<\|[^|]*\|>', '', stream.result.text).strip()

    def feed(self, pcm):
        if self.live is not None:
            self.live.AcceptWaveform(pcm)
        chunk = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        level = float(np.sqrt(np.mean(chunk ** 2))) if chunk.size else 0.0
        loud = level > max(0.012, self.noise * 2.5)
        if not loud:
            self.noise = self.noise * 0.9 + level * 0.1
        secs = chunk.size / SR
        if loud or self.spoke:
            self.buf.append(chunk)
        else:                                 # leading silence: keep a little for the first syllable
            self.buf = (self.buf + [chunk])[-3:]
        if loud:
            self.spoke, self.quiet, self.since = True, 0.0, self.since + secs
            if self.REDO and self.since >= self.REDO:
                self.since, self.text = 0.0, self._decode()
            return False
        if self.spoke:
            self.quiet += secs
            if self.quiet >= self.PAUSE:
                keep = int(self.quiet / (chunk.size / SR))
                del self.buf[len(self.buf) - max(0, keep - 2):]   # the closing silence is not worth decoding
                self.text = self._decode()
                self.spoke = False
                return True
        return False

    def partial(self): return self.text or (self._rough() if self.spoke else '')

    def result(self):
        text, self.text, self.buf = self.text, '', []
        if self.live is not None:
            self.live.Reset()
        return text

    def final(self):
        return self._decode() if self.spoke else self.text


# ---- what was recognized, tidied: joined words, and the person's own names and titles ----

VOCAB_SOURCE = None         # set by the app: a function -> the words (names, titles) this person is likely to say; None = no correction
_RU_PART = ('что|кто|где|когда|куда|как|какой|какая|какое|какие|какую|какого|какому|каких|чей|чья|чьё|почему|зачем|откуда|сколько|'
            'кого|чего|кому|чему|кем|чем')
_RU_SUFFIX = re.compile(r'\b(%s)(нибудь|либо|то)\b' % _RU_PART)
_RU_KOE = re.compile(r'\bкое(%s)\b' % _RU_PART)
_RU_FIXED = {'всетаки': 'все-таки', 'изза': 'из-за', 'изпод': 'из-под', 'потомучто': 'потому что', 'чтоли': 'что ли'}
_EN_NUM = re.compile(r'\b(at|in|on|by|to|for|of|from|until|till|after|before|than|is|was|are|were|about|around)(\d+)\b', re.I)


def tidy(text, lang):
    """Hyphens the Russian model leaves out ("чтонибудь" -> "что-нибудь") and a space the English one drops ("at6" -> "at 6")."""
    text = str(text or '')
    if lang == 'ru':
        text = _RU_SUFFIX.sub(r'\1-\2', _RU_KOE.sub(r'кое-\1', text))
        text = re.sub(r'\b(%s)\b' % '|'.join(_RU_FIXED), lambda m: _RU_FIXED[m.group(1)], text)
    elif lang == 'en':
        text = _EN_NUM.sub(r'\1 \2', text)
    return text


def vocab_fix(text, words):
    """A recognized word that is almost one of the person's own names or titles (one wrong letter) becomes that name. Cautious:
    5+ letters, same first letter, and a different ending of the same word (a case form, "Андрея") is left alone."""
    import difflib
    vocab = {}
    for w in words or []:
        w = str(w).strip()
        if len(w) >= 5 and w.isalpha():
            vocab.setdefault(w.lower(), w)
    if not vocab:
        return text
    out = []
    for token in re.split(r'(\W+)', text):
        low = token.lower()
        if len(low) >= 5 and low.isalpha() and low not in vocab:
            best = None
            for v, shown in vocab.items():
                if v[0] != low[0] or abs(len(v) - len(low)) > 2:
                    continue
                prefix = len(os.path.commonprefix([v, low]))
                if prefix >= min(len(v), len(low)) - 1:      # the same word in another form
                    continue
                score = difflib.SequenceMatcher(None, v, low).ratio()
                if score >= 0.8 and (not best or score > best[0]):
                    best = (score, shown)
            if best:
                token = best[1] if not token[:1].isupper() or best[1][:1].isupper() else best[1].capitalize()
        out.append(token)
    return ''.join(out)


def refine(text, lang):
    text = tidy(text, lang)
    if VOCAB_SOURCE and text:
        try:
            text = vocab_fix(text, VOCAB_SOURCE())
        except Exception:
            pass                                              # a failing vocabulary never costs the sentence
    return text


# ---- how it was said: loudness and pace against the person's own usual (this session only; no audio is kept) ----

_style = ''
_usual = []                 # (loudness, pace) of the last sentences


class Prosody:
    def __init__(self):
        self.t, self.start, self.last, self.noise, self.levels = 0.0, None, 0.0, 0.01, []

    def feed(self, raw):
        raw = np.asarray(raw, dtype=np.float32).reshape(-1)
        level = float(np.sqrt(np.mean(raw ** 2))) if raw.size else 0.0
        secs = raw.size / SR
        self.t += secs
        if level > max(0.01, self.noise * 2.5):
            if self.start is None:
                self.start = self.t - secs
            self.last = self.t
            self.levels.append(level)
        else:
            self.noise = self.noise * 0.9 + level * 0.1

    def describe(self, words):
        """-> '' or a few words ('тише обычного, медленнее обычного'); only a clear difference from his usual is worth saying."""
        if self.start is None or words < 3 or self.last - self.start < 1.0 or len(self.levels) < 8:
            return ''
        import statistics
        loud, pace = statistics.median(self.levels), words / (self.last - self.start)
        parts = []
        if len(_usual) >= 4:
            base_loud, base_pace = statistics.median(a for a, _ in _usual[-20:]), statistics.median(b for _, b in _usual[-20:])
            parts += ['тише обычного'] if loud < base_loud * 0.6 else ['громче обычного'] if loud > base_loud * 1.7 else []
            parts += ['медленнее обычного'] if pace < base_pace * 0.7 else ['быстрее обычного'] if pace > base_pace * 1.4 else []
        _usual.append((loud, pace))
        del _usual[:-40]
        return ', '.join(parts)


STYLE_PARTS = ('тише обычного', 'громче обычного', 'медленнее обычного', 'быстрее обычного')


def last_style():
    return _style


def listen_mic(lang='ru'):
    """Recognize the microphone live until the person has said something and paused; -> the text ('' if nothing was said),
    tidied (see refine). The audio is never stored. Returns None when the recognizer is not ready for this language or was cancelled.
    last_style() then says how it was said."""
    global _style
    code = lang if lang in MODELS else 'en'
    pros = Prosody()
    text = _listen_mic(code, pros)
    if text and echo_of_her(text):          # her own voice: nothing was said by him (the page just listens again)
        text = ''
    if text:
        text = refine(text, code)
        _style = pros.describe(count_words(text))
    else:
        _style = ''
    return text


def _listen_mic(lang, pros):
    global _partial
    lang = lang if lang in MODELS else 'en'
    if _state['status'] != 'ready' or _lang != lang:
        return None
    _cancel.clear()
    _partial = ''
    stream = _new_stream()
    t0, heard, agc = time.time(), False, Agc()
    try:
        with _open_mic() as rec:
            while not _cancel.is_set():
                raw = np.asarray(rec.record(numframes=MIC_STEP), dtype=np.float32).reshape(-1)
                pros.feed(raw)
                data = agc(raw)
                _level['peak'], _level['gain'] = float(np.abs(raw).max()) if raw.size else 0.0, float(agc.gain)
                pcm = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                if stream.feed(pcm):                      # the recognizer heard the sentence end
                    text = stream.result()
                    if text:
                        _partial = ''
                        return text
                    continue
                part = stream.partial()
                if part:
                    heard, _partial = True, part
                elif not heard and time.time() - t0 > MIC_WAIT:
                    return ''
                if time.time() - t0 > MIC_MAX:
                    return stream.final() or _partial
    except Exception as exc:
        _state['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:160])
        raise
    finally:
        _partial = ''
    return None
