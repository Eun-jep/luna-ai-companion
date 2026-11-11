"""The same request must work in all four languages (ru, en, ko, ja): hearing, song, fresh facts, hard questions, tests for code."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app, convo, exact, testgen, reminders
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

ASKS = {
    'hear': (app.EARS_Q, ['слышишь музыку?', 'do you hear that?', '음악 들려?', 'この曲聞こえる？', '지금 뭐 나와?', '今何が流れてる？']),
    'song': (app.SONG_Q, ['что это за песня?', 'what song is this?', '이 노래 뭐야?', 'これ何の曲？', '누가 불러?', '誰が歌ってる？']),
    'sing': (app.SING_ASK, ['спой что-нибудь', 'sing something', '노래 불러줘', '歌って']),
    'fresh': (convo.FRESH, ['какой курс доллара сегодня?', 'what is the exchange rate today?', '오늘 환율 얼마야?', '今日の天気は？', '최신 버전이 뭐야?', '最新ニュースは？']),
    'fact': (convo.FACTUAL, ['в каком году основан Рим', 'what year was Rome founded', '로마는 몇 년에 세워졌어', '日本の首都はどこ', '인구가 얼마야']),
    'hard': (convo.HARD, ['почему это не работает у меня', 'why does this not work for me', '이게 왜 안 되는지 설명해줘', 'なぜ動かないのか説明して']),
}
for name, (rx, phrases) in ASKS.items():
    for ph in phrases:
        ok('%s: %s' % (name, ph), bool(rx.search(ph)))

chat = ['привет, как дела?', 'hi, how are you?', '안녕, 잘 지내?', 'こんにちは、元気？', 'ありがとう', '고마워']
for ph in chat:
    ok('ordinary chat is not a command: ' + ph, not any(rx.search(ph) for k, (rx, _) in ASKS.items() if k in ('hear', 'song', 'fresh', 'hard')))

code = 'def f(x):\n    if x:\n        return 1\n    return 0\n'
for ph in ['напиши тесты', 'write tests', '테스트 써줘', 'テストを書いて']:
    ok('tests for code: ' + ph, 'f(x)' in testgen.analyze(ph + '\n' + code))

# fresh facts: a time word alone is chat; with a question word about the world it is a lookup
for ph in ['сейчас что делаешь?', 'what are you doing now?', '지금 뭐해?', '今何してる？', 'как у тебя сейчас настроение', 'я сегодня устал', '오늘 기분이 좋아', '今日は疲れた']:
    ok('no lookup for chat: ' + ph, not convo.FRESH.search(ph))
for ph in ['кто сейчас президент?', 'who is the president now?', '지금 누구가 대통령이야?', '今誰が首相？', 'какая погода', 'weather in Seoul', '서울 날씨', '東京の天気', 'what is the latest version of python']:
    ok('lookup: ' + ph, convo.FRESH.search(ph))

# her search and open commands in every language, and a file is not a web search
import agent
known = lambda n: n.lower() in ('youtube', 'ютуб', '유튜브')
SEARCH = ['поищи в интернете погоду в Сеуле', 'поищи погоду в интернете', 'search the web for weather', 'google weather', '인터넷에서 날씨 검색해줘', '날씨 알아봐줘', 'ネットで天気を検索して', '東京の天気を調べて', '歌詞を探して']
for ph in SEARCH:
    got = agent.intent_commands(ph, known)
    ok('search: ' + ph, bool(got) and got[0][0] == 'search' and 'интернет' not in got[0][1] and 'web' not in got[0][1] and 'ネット' not in got[0][1] and '인터넷' not in got[0][1])
for ph in ['открой ютуб', 'open youtube', '유튜브 열어줘', 'YouTubeを開いて']:
    ok('open: ' + ph, agent.intent_commands(ph, known)[:1] and agent.intent_commands(ph, known)[0][0] == 'go')
for ph in ['ファイルを探して', '보고서 파일 찾아줘', 'найди файл отчёт в интернете', 'привет, как дела?', 'ありがとう']:
    ok('no web search: ' + ph, agent.intent_commands(ph, known) == [])

# how he talks to her: the small signals work in all four languages, and plain sentences do not trigger them
PRES = {
    'BACKCHANNEL': (convo.BACKCHANNEL, ['ага', 'yeah', 'hmm', '응', '음..', 'そっか', 'なるほど', 'ㅋㅋ'], ['расскажи про погоду', 'tell me about your day', '오늘 뭐 했어', '今日は何をしたの']),
    'EMOTION': (convo.EMOTION_WORDS, ['мне грустно', 'i feel lonely', '너무 외로워', '疲れた', '보고 싶어', '会いたい'], ['какая погода', 'open the file', '파일 열어줘', 'ファイルを開いて']),
    'TEASE': (convo.TEASE, ['ты тупая', 'you are dumb', '바보야', 'バカだな', 'ты же бот'], ['привет', 'hello there', '안녕', 'こんにちは']),
    'WRONG': (convo.WRONG, ['ты ошиблась', "you're wrong", '그건 틀렸어', 'それは違うよ', 'это неправильно'], ['ты права', 'you are right', '맞아', 'そうだね']),
    'THANKS': (convo.THANKS, ['спасибо', 'thank you', '고마워', 'ありがとう', '감사합니다'], ['привет', 'hello', '안녕', 'こんにちは']),
    'LAUGH': (convo.LAUGH, ['хахаха', 'lol that was good', 'ㅋㅋㅋ', '笑', 'あはは'], ['привет', 'hello', '안녕', 'こんにちは']),
    'HURRY': (convo.HURRY, ['мне срочно нужно', 'I am in a rush', '빨리 알려줘', '急いでるんだ', 'коротко скажи'], ['привет', 'hello', '안녕', 'こんにちは', 'расскажи историю']),
    'ANNOYED': (convo.ANNOYED, ['меня это бесит', 'this is so annoying', '짜증나', 'イライラする', 'опять не работает'], ['привет', 'hello', '안녕', 'こんにちは', 'мне нравится дождь']),
    'CLICHE_SENTENCE': (convo.CLICHE_SENTENCE, ['Чем могу помочь?', 'How can I help you?', '무엇을 도와드릴까요', '何かお手伝いできますか'], ['Мне нравится дождь.', 'I like rain.', '비가 좋아.', '雨が好き。']),
    'CLICHE_OPENER': (convo.CLICHE_OPENER, ['Конечно, ', 'Of course, ', '물론이죠, ', 'もちろん、'], ['Нет, ', 'No, ', '아니, ', 'いや、']),
}
for name, (rx, yes, no) in PRES.items():
    for ph in yes:
        ok('%s: %s' % (name, ph), rx.search(ph))
    for ph in no:
        ok('%s is not triggered by: %s' % (name, ph), not rx.search(ph))
ok('opener is cut in ko', convo.CLICHE_OPENER.sub('', '물론이죠, 좋아요.') == '좋아요.')
ok('opener is cut in ja', convo.CLICHE_OPENER.sub('', 'もちろん、いいよ。') == 'いいよ。')

# he reminds her he already said it
for ph in ['я же тебе говорил про это', 'ты забыла?', 'I told you already', 'you forgot', '내가 이미 말했잖아', '너 잊었어?', 'もう言ったでしょ', '覚えてないの？']:
    ok('TOLD: ' + ph, convo.TOLD.search(ph))
for ph in ['расскажи про погоду', 'tell me a story', '이야기해줘', '話して', 'привет, как дела?']:
    ok('TOLD is not triggered by: ' + ph, not convo.TOLD.search(ph))
for ph in ['я же тебе говорил, что у меня кот', 'I told you I have a cat', '내가 이미 말했잖아, 고양이 있어', 'もう言ったでしょ、猫がいる']:
    ok('hint for a reminder: ' + ph, 'уже говорил' in str(convo.hints([], ph)))

# the same question twice: she must not repeat herself (any language)
H = lambda q: [{'role': 'user', 'content': q}, {'role': 'assistant', 'content': 'ответ'}]
for q1, q2 in [('как работает блокчейн на самом деле', 'ну так как работает блокчейн на самом деле'), ('how does the blockchain really work', 'so how does the blockchain really work'),
               ('블록체인 어떻게 작동 해요 정말', '그래서 블록체인 어떻게 작동 해요 정말'), ('ブロックチェーン 仕組み 教えて 本当に', 'ブロックチェーン 仕組み 教えて 本当に')]:
    ok('asked again: ' + q2, convo.asked_again(H(q1), q2) and 'прошлый ответ не дошёл' in str(convo.hints(H(q1), q2)))
ok('another question is not a repeat', not convo.asked_again(H('как работает блокчейн на самом деле'), 'какая сегодня погода в Сеуле'))
ok('too short is not a repeat', not convo.asked_again(H('да'), 'да'))
ok('worn words in ko and ja', convo.worn_words(['바다가 좋아요 바다 하늘 노을', '바다 하늘 노을 같이 봐요', '하늘 노을 바다 멋져요']) != [])

# a reminder she cannot give: the honest-no hint in every language, and none for plain chat
for ph in ['напомни мне через 10 минут про чай', 'remind me to call mom', '10분 뒤에 알려줘', '알람 맞춰줘', 'リマインドして', '30分後に教えて']:
    ok('REMIND: ' + ph, convo.REMIND.search(ph) and ('Не обещай' in str(convo.hints([], ph))) != bool(reminders.parse(ph)))   # a time she can keep: set; else the honest no
for ph in ['расскажи про чай', 'tell me about tea', '차 얘기해줘', 'お茶の話をして', 'ты помнишь меня?']:
    ok('REMIND is not triggered by: ' + ph, not convo.REMIND.search(ph))

# his hurry and irritation reach her as hints, in every language
for ph in ['мне срочно нужен ответ про рецепт', 'I am in a rush, what time is it in Seoul', '빨리 알려줘 이거 어떻게 해', '急いでるから手短に教えて']:
    ok('hurry hint: ' + ph, 'торопится' in convo.hints([], ph, pick=None))
for ph in ['меня бесит этот принтер, опять не работает', 'this printer is so annoying today', '프린터 때문에 짜증나', 'プリンターがうまくいかなくてイライラする']:
    ok('annoyed hint: ' + ph, 'раздражён' in convo.hints([], ph, pick=lambda r: list(r)[-1]))
ok('teasing is not irritation', 'раздражён' not in convo.hints([], 'ты тупая, бесит', pick=lambda r: list(r)[-1]))

# the tone of his words (rude / sorry / thanks / sad / angry / tired / happy) is read in all four languages, and plain chat has none
import character as _C
TONE_CASES = [
    ('rude', ['ты тупая, заткнись', 'shut up', '닥쳐', '黙れ']),
    ('sorry', ['прости меня', "i'm sorry", '미안해', 'ごめんね']),
    ('thanks', ['спасибо тебе', 'thank you so much', '고마워', 'ありがとう']),
    ('sad', ['мне так грустно', 'i feel lonely', '너무 외로워', '寂しいよ']),
    ('angry', ['меня это бесит', 'i am so angry', '진짜 화나', 'ムカつく']),
    ('sick', ['у меня болит голова', 'i have a fever', '감기 걸렸어', '風邪ひいた']),
    ('tired', ['я ужасно устал', 'i am exhausted', '너무 피곤해', '疲れた']),
    ('happy', ['ура, получилось', 'yay, so happy', '야호 합격했어', 'やった、嬉しい']),
]
for want, phrases in TONE_CASES:
    for ph in phrases:
        ok('tone %s: %s' % (want, ph), _C.sense(ph) == want)
for ph in ['какая погода', 'what is the weather', '오늘 날씨 어때', '今日は何をしたの', '안녕', 'こんにちは']:
    ok('no tone in plain chat: ' + ph, _C.sense(ph) == '')

# how he writes: smiles and swearing are seen in all four languages too
for ph in ['ахах ну ты даёшь', 'lol :)', 'ㅋㅋ 웃겨', 'あはは、それは笑']:
    ok('smile seen: ' + ph, bool(_C.EMOJI_RE.search(ph)))
for ph in ['блин, опять', 'damn it', '젠장', 'くそ、また']:
    ok('swear seen: ' + ph, bool(_C.SWEAR_RE.search(ph)))
for ph in ['привет', 'hello', '안녕', 'こんにちは']:
    ok('no smile or swear in a greeting: ' + ph, not _C.EMOJI_RE.search(ph) and not _C.SWEAR_RE.search(ph))


# ---- farewell and greeting rituals: a short goodbye / hello in all four languages, and long talk or questions do not count ----
for ph in ['спокойной ночи', 'я спать, пока', 'good night!', "gotta go, talk later", '잘 자~', '자러 갈게', 'おやすみ', 'またね', 'пока', 'bye', '바이바이', 'じゃあね']:
    ok('farewell: ' + ph, convo.parting(ph) == 'bye')
for ph in ['доброе утро', 'привет!', 'good morning', 'hey', 'hi', '좋은 아침', '안녕', '나 왔어', 'おはよう', 'ただいま', 'こんばんは', 'я вернулся']:
    ok('greeting: ' + ph, convo.parting(ph) == 'hello')
for ph in ['какая погода', 'what is the weather', '오늘 날씨 어때', '今日は何をしたの', 'пока не знаю, что делать', 'привет, как у тебя дела?',
           'вчера я лёг спать очень поздно и потом долго думал о работе', 'I went to bed late and thought about work for hours', '']:
    ok('not a ritual: ' + ph, convo.parting(ph) == '')
h = convo.hints([], 'спокойной ночи')
ok('a goodnight gets the family farewell hint', 'прощается' in h and 'новую тему' in h)
h = convo.hints([], 'おはよう')
ok('a good morning gets the greeting hint', 'здоровается' in h)
h = convo.hints([], 'расскажи про погоду в Сеуле завтра')
ok('plain talk gets neither', 'прощается' not in h and 'здоровается' not in h)

# the server's own error messages reach him in his language: every message the page knows has a sentence in all four languages,
# and every such message still exists in app.py (so the table cannot silently rot)
import re as _re
_i18n = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web', 'i18n.js'), encoding='utf-8').read()
_prov = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web', 'provider.js'), encoding='utf-8').read()
_app = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.py'), encoding='utf-8').read()
_pairs = _re.findall(r"\[\s*'([^']+)',\s*'(srv\.\w+)'\s*\]", _prov)
ok('the error table is not empty', len(_pairs) >= 12)
for _ru, _key in _pairs:
    ok('server message still in app.py: ' + _ru[:30], _ru in _app)
    ok('translated in all four languages: ' + _key, _i18n.count("'%s':" % _key) == 4)


# questions: a full-width ？ counts, her Japanese questions are seen, and Korean/Japanese questions without a mark are noticed
for ph in ['元気？', '今日はどうだった？', 'これ何ですか。', '오늘 뭐 했어?', '밥 먹었나요', 'ты где?', 'what now?!']:
    ok('he asks: ' + ph, convo.kind_of(ph)['question'])
for ph in ['元気だよ。', '오늘은 피곤해', 'я устал', 'I am fine']:
    ok('he states: ' + ph, not convo.kind_of(ph)['question'])
for ph in ['どう思う？', 'どう思う？！', '어떻게 생각해?', 'как думаешь?', 'what do you think?', 'ね、元気？」']:
    ok('her line ends with a question: ' + ph, convo.ends_question(ph))
for ph in ['そうなんだ。', '좋아.', 'ладно.', 'ok', '']:
    ok('her line is not a question: ' + ph, not convo.ends_question(ph))
_h = [{'role': 'assistant', 'content': 'どう思う？'}, {'role': 'user', 'content': 'それはどういう意味？'}, {'role': 'assistant', 'content': 'えっと、つまりね。'}]
ok('a hanging question is seen in Japanese', 'どう思う' in convo.open_question(_h))
_m = convo.hints([{'role': 'assistant', 'content': 'どう思う？'}, {'role': 'user', 'content': 'うーん'}, {'role': 'assistant', 'content': '元気？'}, {'role': 'user', 'content': 'まあ'}, {'role': 'assistant', 'content': '何してた？'}], '寝てた')
ok('three Japanese questions in a row: the quota hint fires', 'вопроса не задавай' in _m)


# the opening words of her replies (to vary them): two words, or the first letters of a Japanese reply that has no spaces
ok('opening, Russian', convo.opening('Ну, давай посмотрим вместе.') == 'ну, давай' or convo.opening('Ну, давай посмотрим вместе.') == 'ну')
ok('opening, English', convo.opening('Well, let us see together.') in ('well, let', 'well'))
ok('opening, Korean', convo.opening('음, 같이 볼까요?') in ('음', '음, 같이'))
ok('opening, Japanese is short, not the whole sentence', len(convo.opening('そうなんだ、それは大変だったね。')) <= 5)
ok('opening, a Japanese reply without any comma is cut', len(convo.opening('それは本当に大変だったでしょうね今日は')) <= 4)
_ex = convo.hints([{'role': 'assistant', 'content': 'すごい！'}, {'role': 'user', 'content': 'うん'}, {'role': 'assistant', 'content': 'やった！'}, {'role': 'user', 'content': 'そう'}, {'role': 'assistant', 'content': '最高！'}], '寝る前に')
ok('full-width exclamations count as exclamations', 'без «!» через раз' in _ex)


# the length of a message in Japanese (no spaces) is counted by letters, so a long story is "long", not one short word
_jl = '今日は朝から雨が降っていて、仕事に行く前に友達から連絡があって、久しぶりに会おうという話になったんだけど、夜まで予定が詰まっていて返事を迷っている'
ok('a long Japanese message is long', convo.kind_of(_jl)['size'] == 'long' and convo.count_words(_jl) > 25)
ok('a very short Japanese message is short', convo.kind_of('寝るね')['size'] in ('short', 'back') and convo.count_words('寝るね') <= 2)
ok('a middle Japanese message is normal', convo.kind_of('今日は友達とご飯を食べに行ってきたよ')['size'] == 'normal')
ok('Russian and Korean are still counted by spaces', convo.count_words('привет как дела у тебя') == 5 and convo.count_words('오늘 뭐 했어') == 3)
ok('a long Japanese story does not get "he wrote briefly"', 'написал коротко' not in convo.hints([], _jl))
ok('a short Japanese message still does', 'коротко' in convo.hints([], '寝るね'))
convo.STYLE.update({'n': 0, 'words': 0.0, 'casual': 0.0})
for _m in ['ねむい', 'おなかすいた', 'まあいいか', 'つかれたー', 'やばい']:
    convo.observe(_m)
ok('careless Japanese chat is recognised as casual', convo.STYLE['casual'] > 0.6 and convo.style_hint() != '')
convo.STYLE.update({'n': 0, 'words': 0.0, 'casual': 0.0})


# words that can be about something else must not hurt her: a noisy neighbour, a food he hates, himself
for ph in ['隣の人がうるさい', 'ラーメンが大嫌い', '나는 쓸모없어', '내가 한심해', '今日の自分は役立たずだった', 'the neighbours are so loud']:
    ok('not rude towards her: ' + ph, _C.sense(ph) != 'rude')
for ph in ['너 진짜 쓸모없어', '너 싫어', 'お前なんか大嫌い', 'あなたが嫌い', 'お前は役立たず']:
    ok('rude towards her: ' + ph, _C.sense(ph) == 'rude')


# ---- the language-practice mode: switched on and off in words in all four languages, plain chat never switches it ----
import tempfile as _tf, pathlib as _pl
_C.MEMORY_FILE = _pl.Path(_tf.mkdtemp()) / 'memory.json'   # never her real memory
for ph in ['поправляй мои ошибки', 'correct my mistakes please', '내 실수 고쳐줘', '間違いを直して', 'я учу корейский, поправляй меня', 'i am learning korean, please correct me', '添削して']:
    _C.MEMORY['tutor'] = 0
    ok('tutor on: ' + ph, _C.note_tutor(ph) == 'on' and _C.MEMORY['tutor'] == 1 and 'ошибки' in _C.tutor_hint('on') and 'только что включил' in _C.tutor_hint('on'))
for ph in ['хватит меня поправлять', 'stop correcting me', '그만 고쳐줘', '直さなくていいよ', 'не поправляй']:
    _C.MEMORY['tutor'] = 1
    ok('tutor off: ' + ph, _C.note_tutor(ph) == 'off' and _C.MEMORY['tutor'] == 0 and _C.tutor_hint('off').startswith(' [Он попросил'))
for ph in ['какая погода', 'what is the weather', '오늘 날씨 어때', '今日は何をしたの', 'я поправил полку', 'I corrected the code']:
    _C.MEMORY['tutor'] = 0
    ok('plain chat does not switch it on: ' + ph, _C.note_tutor(ph) == '' and _C.MEMORY['tutor'] == 0 and _C.tutor_hint() == '')
_C.MEMORY['tutor'] = 1
ok('while on, every answer carries the gentle-correction hint', 'мягко покажи' in _C.tutor_hint() and 'не экзаменатор' in _C.tutor_hint())
ok('switching off when already off says nothing', (_C.MEMORY.__setitem__('tutor', 0), _C.note_tutor('stop correcting'))[1] == '')
_C.save_memory(); _C.MEMORY['tutor'] = 1; _C.load_memory()
ok('the mode survives a restart only if it was saved on', _C.MEMORY['tutor'] == 0)
_C.MEMORY['tutor'] = 1; _C.save_memory(); _C.MEMORY['tutor'] = 0; _C.load_memory()
ok('...and is kept when it was on', _C.MEMORY['tutor'] == 1)
_C.MEMORY['tutor'] = 0
