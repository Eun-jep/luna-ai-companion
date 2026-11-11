"""Self-check of her claims about him. When she says "you told me...", "I remember you...", the program looks for the substance of
the claim in what she really knows (his facts, the summary, his own messages). A claim with no trace is not blocked: she is quietly
told on her next turn, so that she owns up to it in one phrase instead of building on a made-up memory."""
import re
import lexicon

CLAIM = lexicon.rx('recall')
SENTENCE = re.compile(r'(?<=[.!?…。！？])\s*')
TOKEN = re.compile(r'[^\W\d_]{4,}|[가-힣ぁ-んァ-ヶ一-龥]{2,}')
CJK = re.compile(r'[가-힣ぁ-んァ-ヶ一-龥]')
PLAIN = {'тебя', 'тебе', 'меня', 'мне', 'этого', 'этот', 'когда', 'потому', 'просто', 'только', 'очень', 'that', 'this', 'with', 'what', 'when', 'have', 'about', 'there'}
NEEDED = 0.5   # share of the claim's words that must be found in what she knows


def _found(token, haystack):
    if CJK.match(token):
        pairs = [token[i:i + 2] for i in range(max(1, len(token) - 1))]
        return sum(1 for p in pairs if p in haystack) >= max(1, len(pairs) // 2)
    return token[:5] in haystack


def ungrounded(reply, known):
    """The first sentence of the reply that claims to recall something of his that nothing she knows supports, or ''."""
    haystack = ' '.join(str(k) for k in known).lower()
    for sentence in SENTENCE.split(str(reply or '')):
        sentence = re.sub(r'\[[^\]]*\]', '', sentence).strip()
        m = CLAIM.search(sentence)
        if not m:
            continue
        words = [t.lower() for t in TOKEN.findall(sentence[:m.start()] + ' ' + sentence[m.end():]) if t.lower() not in PLAIN]
        if not words:
            continue   # nothing specific is claimed
        if sum(1 for w in words if _found(w, haystack)) < len(words) * NEEDED:
            return sentence[:160]
    return ''


def doubt_hint(sentence):
    return ('В прошлой реплике ты сказала «%s», но в том, что ты помнишь о нём, и в разговоре этого нет. Если ты это придумала или перепутала, '
            'признайся одной лёгкой фразой («стоп, кажется, я это сама сочинила»), без драмы и не извиняясь на три абзаца; не строй на этом дальше. '
            'Если это была явная шутка, ничего не надо.' % sentence)
