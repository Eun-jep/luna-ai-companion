"""The emotion of her own sentence, read from the words, for the replies where the model wrote no [emotion] tag.
Only a clear signal counts (a warm thanks, a sorry, a startled "ой!"); anything ambiguous stays untouched, so the face is never
forced into a mood the sentence does not show. A tag the model did write always wins: this is consulted only when there is none."""
import re

from luna.core.script import EMOTIONS

TAG = re.compile(r'\[(\w+)(?::[^\]]*)?\]')

# emotion -> patterns; the first emotion whose pattern matches wins, so the more specific ones come first
RULES = [
    ('love', re.compile(r"(?:люблю тебя|тебя люблю|обожаю|ты мне (?:очень )?дорог|скучала|i love you|i missed you|miss you|사랑해|보고 싶|好きだよ|会いたかった)", re.I)),
    ('scared', re.compile(r"(?:мне страшно|боюсь|испугалась|i'?m (?:scared|afraid)|무서워|怖い)", re.I)),
    ('angry', re.compile(r"(?:злюсь|бесит|возмутительно|i'?m (?:angry|furious)|화나|腹が立)", re.I)),
    ('sad', re.compile(r"(?:мне грустно|грустно|жаль,? что|к сожалению|прости(?:те)?,? что|извини(?:те)?|мне очень жаль|i'?m (?:so )?sorry|that'?s sad|unfortunately|슬퍼|미안해|죄송|悲しい|ごめん)", re.I)),
    ('surprised', re.compile(r"(?:^|[\s(])(?:ого+|ничего себе|неужели|вот это да|вау|wow|whoa|no way|세상에|대박|えっ|うそ|まさか)(?=[\s!?.,…]|$)", re.I)),
    ('shy', re.compile(r"(?:смущаюсь|ой, ну что ты|мне неловко|приятно слышать|you'?re making me blush|부끄러|恥ずかしい)", re.I)),
    ('excited', re.compile(r"(?:ура+\b|здорово!|круто!|класс!|потрясающе|отлично!|awesome!|yay|hooray|amazing!|신나|やった|すごい!)", re.I)),
    ('happy', re.compile(r"(?:рада (?:тебя|тебе|что|за)|спасибо|благодарю|поздравляю|счастлива|приятно|i'?m (?:so )?(?:glad|happy)|thank you|thanks|congrat|기뻐|고마워|감사|嬉しい|ありがとう|おめでとう)", re.I)),
    ('confused', re.compile(r"(?:не понимаю|не уверена|странно[.,]|хм+[.…]|i'?m not sure|i don'?t understand|hmm+[.…]|모르겠|잘 모르|わからない)", re.I)),
]


def has_emotion_tag(script):
    """Whether the stage directions already carry an emotion ([happy], [sad], ...)."""
    return any(m.group(1) in EMOTIONS for m in TAG.finditer(script or ''))


def infer(text):
    """-> an emotion name when the sentence clearly shows one, else None."""
    text = (text or '').strip()
    if len(text) < 3:
        return None
    for emotion, rule in RULES:
        if rule.search(text):
            return emotion
    return None


def tag_for(script, spoken, seen):
    """The [emotion] to put in front of this sentence, or ''. seen: an emotion tag was already written earlier in this reply
    (a tag stays in force until the next one, so nothing is added then)."""
    if seen or has_emotion_tag(script):
        return ''
    emotion = infer(spoken)
    return '[%s]' % emotion if emotion else ''
