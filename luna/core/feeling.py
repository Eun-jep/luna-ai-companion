"""The tone of his words by meaning, not by the words themselves: «меня всё достало» and «it's been a rough week» carry sadness without any word from a list.

It works only when a real embedding model is connected: local Ollama (settings.json: "embeddings": "ollama:nomic-embed-text") or, if the user turned it on in the settings, the cloud service she already uses (Gemini, OpenAI); see character.use_embeddings.
Then the message is compared with a few example sentences per tone (four languages); the nearest tone wins if it is clearly closer than everyday talk.
Without such a model it does nothing: the offline word-form vectors know nothing of meaning, and a guess would only put wrong feelings into her.
character.sense() asks this only when its word lists found no tone. The thresholds were measured on nomic-embed-text with 52 labelled phrases (no false alarms, no wrong tone, about half of the real ones found); another model needs its own look: tools/feeling_check.py prints the scores for your phrases.
Rude is never guessed from meaning: an offence is remembered and hurts, so it needs words. Nothing here leaves the computer unless the cloud option is on."""
import threading
import time

from luna.core import memory_store

FLOOR = 0.35          # as in memory_store.similarities: below it two texts share only the ordinary words of the language
MIN_SIM = 0.45        # how close to an example the message must be (0..1 after the floor)
MARGIN = 0.18         # and how much closer than to everyday talk (measured on nomic-embed-text, see CHANGELOG: 0.05 gave false alarms and wrong tones)
MIN_CHARS, MAX_CHARS = 6, 300
COOLDOWN = 60         # seconds without trying again after the model failed

EXAMPLES = {
    'sad': ['I feel so down today', 'I am really sad and lonely', 'it has been a rough week and nothing goes right', 'everything is falling apart for me',
            'мне очень грустно и одиноко', 'всё валится из рук, ничего не радует', 'на душе тяжело, хочется плакать',
            '너무 우울하고 외로워', '요즘 모든 게 힘들고 지쳐', '最近ずっと落ち込んでいて寂しい', '何もかもうまくいかなくて辛い'],
    'angry': ['I am so angry right now', 'this is infuriating, I am fed up with all of it', 'they ruined everything and I am furious',
              'меня всё бесит, я в ярости', 'как же меня достало это всё', '너무 화가 나고 짜증나', '정말 열받아', '腹が立って仕方ない', 'もう本当にイライラする'],
    'sick': ['I am sick, my head hurts and I have a fever', 'I feel terrible, I think I caught a cold', 'я заболел, болит голова и температура',
             'мне нездоровится, всё болит', '몸이 안 좋아, 열이 나고 머리가 아파', '体調が悪くて熱がある'],
    'tired': ['I am exhausted, I barely slept', 'I have no energy left today', 'я безумно устал, нет сил', 'я совсем без сил после работы',
              '너무 피곤해서 힘이 하나도 없어', 'もうくたくたで力が出ない'],
    'happy': ['I am so happy today, everything went great', 'wonderful news, I got the job', 'сегодня отличный день, я так рад', 'у меня получилось, я счастлив',
              '오늘 정말 기분 좋아, 잘 됐어', '今日はとても嬉しい、うまくいった'],
    'thanks': ['thank you so much for your help', 'I really appreciate what you did for me', 'спасибо тебе огромное, ты меня выручила', 'очень благодарен тебе за помощь',
               '정말 고마워, 큰 도움이 됐어', '本当にありがとう、助かった'],
}
EVERYDAY = ['what is the weather like', 'can you open the calendar', 'tell me something about cats', 'what time is it', 'let us talk about the book',
            'какая сегодня погода', 'расскажи что-нибудь про космос', 'давай обсудим проект', 'открой, пожалуйста, браузер', 'что у нас на сегодня',
            '오늘 날씨 어때', '이 문서를 요약해 줘', '今日の予定を教えて', '次の話題に進もう']

_lock = threading.Lock()
_pool = {}            # embedder name -> {tone: [vectors]}
_failed = [0.0]
_warming = set()


def _vectors(name, phrases):
    out = []
    for p in phrases:
        n, v = memory_store.vector(p)
        if v is None or n != name:
            return None
        out.append(v)
    return out


def _build(name):
    memory_store.prefetch([p for phrases in (*EXAMPLES.values(), EVERYDAY) for p in phrases])   # a cloud embedder takes them in one request
    sets = {tone: _vectors(name, phrases) for tone, phrases in {**EXAMPLES, '': EVERYDAY}.items()}
    with _lock:
        _warming.discard(name)
        if any(v is None for v in sets.values()):
            _failed[0] = time.time()
        else:
            _pool[name] = sets


def warm(name):
    """Embed the examples in the background (about sixty short texts, once: memory_store keeps them), so that no chat turn waits for it."""
    with _lock:
        if name in _pool or name in _warming:
            return
        _warming.add(name)
    threading.Thread(target=_build, args=(name,), daemon=True).start()


def _close(vec, vectors):
    return max(max(0.0, (memory_store.cosine(vec, v) - FLOOR) / (1 - FLOOR)) for v in vectors)


def scores(text):
    """-> {tone: closeness 0..1} (the key '' is everyday talk), or None when there is no real embedding model or it failed."""
    if time.time() - _failed[0] < COOLDOWN:
        return None
    name, vec = memory_store.vector(text)
    if vec is None:
        if name is None and memory_store._embedder:
            _failed[0] = time.time()
        return None
    with _lock:
        pool = _pool.get(name)
    if pool is None:
        warm(name)   # not ready yet: this turn goes by the word lists only
        return None
    return {tone: _close(vec, vectors) for tone, vectors in pool.items()}


def classify(text):
    """The tone of the text by meaning: one of EXAMPLES' keys, or '' (nothing clear, no embedding model, or everyday talk)."""
    text = ' '.join(str(text or '').split())
    if not MIN_CHARS <= len(text) <= MAX_CHARS or not memory_store._embedder:
        return ''
    got = scores(text)
    if not got:
        return ''
    tone = max((t for t in got if t), key=got.get)
    return tone if got[tone] >= MIN_SIM and got[tone] - got[''] >= MARGIN else ''


def reset():
    with _lock:
        _pool.clear()
        _warming.clear()
    _failed[0] = 0.0
