"""One place for the words of what he asks, in all four languages (ru, en, ko, ja).
Every spoken request that the program recognises by words (hearing, a song, fresh facts, a hard question) takes its words from here, so a new
language or word is added once and a request can never work in two languages and silently fail in the other two. tests/test_langs.py checks
the same request in all four.
Each concept is {language: regex fragment}; rx() joins them into one case-insensitive pattern."""
import re

LANGS = ('ru', 'en', 'ko', 'ja')

WORDS = {
    # does she hear what plays / which song is it
    'hear': {
        'ru': r'слышишь|слышно|слышала|что (сейчас |это )?(играет|звучит|за (музык|песн|трек))|как называется (эта |этот )?(песн|трек|музык|мелоди)|кто (это )?(поёт|поет|исполня)|узнаёшь (песн|музык|трек)|узнаешь (песн|музык|трек)',
        'en': r'do you hear|what.s playing|can you hear|hear (this|that|it)|what song|who sings',
        'ko': r'들려|들리|들을 수|뭐 나와|무슨 (노래|음악|곡)|이 (노래|곡|음악)|누가 (불러|부르)',
        'ja': r'聞こえ|聴こえ|聞いて|何が流れ|何の(曲|歌|音楽)|この(曲|歌|音楽)|誰が歌',
    },
    'song': {
        'ru': r'что (это )?за (песн|трек|музык)|как называется|кто (это )?(поёт|поет|исполня)|узнаёшь|узнаешь',
        'en': r'what song|name of (this|the) song|who sings|what.s (this|the) song',
        'ko': r'무슨 (노래|곡)|이 (노래|곡)|제목|누가 (불러|부르)|가수',
        'ja': r'何の(曲|歌)|この(曲|歌)|曲名|タイトル|誰が歌|歌手',
    },
    # facts that go stale: the program makes her look them up. Time words alone ("now", "today") do not count: see weak_fresh()
    'fresh': {
        'ru': r'на данный момент|последн\w+ верси|новост|погод|курс\b|цен[аыуе]\b|сколько стоит|стоит ли купить|когда выйд|вышел[аои]? ли|кто сейчас|актуальн|в 202\d',
        'en': r'latest|current price|exchange rate|weather|news\b|how much (is|does)|price of|new version|release date',
        'ko': r'최신|환율|가격|얼마|뉴스|날씨|버전|출시',
        'ja': r'最新|為替|レート|価格|いくら|ニュース|天気|バージョン|発売',
    },
    'fresh_time': {
        'ru': r'сегодня|сейчас|на этой неделе',
        'en': r'today|\bnow\b|this week|currently',
        'ko': r'오늘|지금|현재|이번 주',
        'ja': r'今日|今|現在|今週',
    },
    'fresh_wh': {   # a question word next to a time word: "who is president now" is a lookup, "what are you doing now" is chat
        'ru': r'кто|что|какой|какая|какие|сколько|когда|где',
        'en': r'who|what|which|when|where|how much|how many',
        'ko': r'누구|무엇|뭐가|어느|어떤|얼마|언제|어디',
        'ja': r'誰|何が|どの|どれ|いくら|いつ|どこ',
    },
    'fresh_chat': {   # about her or him, not about the world
        'ru': r'делаешь|делал[аи]?|чувствуешь|как (ты|дела)|настроени',
        'en': r'are you doing|you doing|do you feel|how are you|your mood',
        'ko': r'뭐해|뭐 해|뭐하|기분|잘 지내',
        'ja': r'何してる|何をして|どうしてる|気分|元気',
    },
    'factual': {
        'ru': r'в каком году|когда (был|была|было|родил|основан)|сколько (лет|людей|жителей|км|метров|человек)|кто (написал|придумал|изобрёл|изобрел|основал)|столица|население|как называется|правда ли|точно ли|\bфакт',
        'en': r'what year|who (wrote|invented|founded)|capital of|population|is it true',
        'ko': r'몇 년|누가 (썼|만들|발명|세웠)|수도|인구|사실이야|진짜야',
        'ja': r'何年|誰が(書|作|発明|設立)|首都|人口|本当|事実',
    },
    # a question that wants reasoning, not chat
    'hard': {
        'ru': r'почему|зачем|как (работает|устроен|правильно|лучше|сделать|исправить)|объясни|сравни|в чём разница|что лучше|посоветуй|помоги разобраться|не работает|ошибка|баг|посчитай|докажи',
        'en': r'how does|why does|explain|how (do|can|should) i|what.s the difference|compare|not working',
        'ko': r'왜|어떻게|설명|차이|비교|안 (돼|되|된)|오류|버그|추천',
        'ja': r'なぜ|どうして|どうやって|説明|違い|比較|動かない|エラー|バグ|おすすめ',
    },
    # how he talks to her: the small signals that make her answer like a person (short reply to a backchannel, warmth to a heavy word, ...)
    'backchannel': {
        'ru': r'ага|угу|мгм|ну|хм+|ясно|понятно|ок(ей)?|окей|ладно|да|нет|ха(-?ха)*|лол|ммм*|ого|вау|круто|ну да|так себе|норм|ничего|ничё',
        'en': r'aha|yeah|yep|yes|nope|no|ok(ay)?|hmm+|mhm|lol|wow|cool|nice|sure|right|i see|got it|fine|same|oh',
        'ko': r'응|음+|어|그래|알겠어|알았어|오케이|좋아|아니|맞아|헐|와+|대박|ㅋ+|ㅎ+|그렇구나|괜찮아|그냥',
        'ja': r'うん|ええ|はい|いいえ|そうか|そっか|なるほど|了解|オッケー|わかった|へえ|すごい|やった|笑|w+|ｗ+|まあね|そうだね|ふーん',
    },
    'emotion': {
        'ru': r'груст|плохо|одинок|страшно|боюсь|тревож|устал|выгор|плач|не хочу|обидно|бесит|злюсь|зла|умер|болезн|больно|депресс|ненавижу|не получается|сдался|скучаю|рад|счастлив|ура|получилось|сдал|выиграл|люблю|влюб',
        'en': r'sad|lonely|tired|scared|anxious|angry|happy|proud|depress|miss you|love you|exhaust|stress|worried|excited|crying|hurts|afraid|upset|furious|passed|i won|i quit|give up',
        'ko': r'슬퍼|슬프|우울|외로|무서|걱정|피곤|지쳤|화나|짜증|아파|죽고 싶|보고 싶|사랑|행복|기뻐|신나|합격|성공했|힘들|포기',
        'ja': r'悲しい|寂しい|さみしい|怖い|不安|疲れ|辛い|つらい|腹が立|イライラ|痛い|死にたい|会いたい|好き|愛し|嬉しい|幸せ|やった|合格|成功した|うつ|諦め',
    },
    'tease': {
        'ru': r'тупая|глупая|дурочка|дурында|балда|тормоз|бот\b|железка|ничего не умеешь|ты (что|чё)|ха-?ха.{0,20}ты|смешная|тостер|кринж|ну ты даёшь|ну ты и|лол.{0,10}ты|ты же (ии|бот|нейросеть)',
        'en': r'dumb|silly|stupid|you suck|nice try|toaster|just a bot|you.re a bot|cringe|useless',
        'ko': r'바보|멍청|로봇|기계|토스터|쓸모없|못하네|너 뭐야',
        'ja': r'バカ|ばか|アホ|ロボット|機械|トースター|役立たず|ダメだな|何それ',
    },
    'wrong': {   # he says she got it wrong
        'ru': r'ты (ошиб|не права|неправ|путаешь|перепутала)|это неправильно|неверно|не так\b|это не то\b|неправда',
        'en': r'you.re wrong|that.s (wrong|not (right|true))|incorrect|you (made a mistake|got it wrong|mixed)|not what i (meant|said)',
        'ko': r'틀렸|잘못(됐|된|알)|그게 아니|네가 틀|오답|사실이 아니',
        'ja': r'間違(って|い)|違うよ|それは違|ちがうよ|誤り|事実じゃない',
    },
    'told': {   # he reminds her he already said it: she forgot something
        'ru': r'я (же )?(тебе )?(уже )?(говорил|рассказывал|писал|упоминал)|ты (забыла|не помнишь)|я уже сказал|мы же (говорили|обсуждали)|ты не запомнила',
        'en': r'i (already )?(told|said|mentioned) you|you forgot|don.t you remember|we (already )?(talked|discussed)|i just said',
        'ko': r'(내가|제가) (이미 )?(말했|얘기했|이야기했)|(너|넌) 잊었|기억 안 나|기억 못|벌써 말했|우리 (얘기|이야기)했잖',
        'ja': r'(もう|前に)(言った|話した|伝えた)|忘れた(の|んだ)|覚えて(ない|いない)|さっき言った|話したじゃん|言ったでしょ',
    },
    'remind': {   # he asks her to remind him later: she cannot (no timers), so she must not promise it
        'ru': r'напомни|напоминай|разбуди|поставь (будильник|таймер)|через \d+ (мин|час)\w* (скажи|напомни)',
        'en': r'remind me|wake me|set (an? )?(alarm|timer)|ping me (in|at|tomorrow)',
        'ko': r'(분|시간) ?(뒤|후)에.{0,20}(알려|말해)|깨워|알람|타이머|리마인드|(이따|나중에) 알려|\d ?시(에| 반에)? (알려|말해)|내일.{0,14}(알려|말해)',
        'ja': r'リマインド|思い出させて|起こして|アラーム|タイマー|(後で|あとで)教えて|分後に.{0,20}(教えて|知らせて|思い出させて)|時(半)?に(教えて|知らせて)|(明日|あした).{0,14}(教えて|知らせて)',
    },
    'thanks': {
        'ru': r'спасибо|спс|благодарю',
        'en': r'thanks|thank you|thx|appreciate',
        'ko': r'고마워|고맙|감사|땡큐',
        'ja': r'ありがと|感謝|サンキュ',
    },
    'laugh': {
        'ru': r'ха-?ха|ахах|хах|лол|ржу|кек',
        'en': r'\blol\b|haha|lmao|hehe|rofl',
        'ko': r'ㅋ{2,}|ㅎ{2,}|ㅋㅎ|웃겨',
        'ja': r'笑|草|ｗｗ|ははは|あはは|うける',
        'any': r'www|😂|🤣',
    },
    'hurry': {
        'ru': r'срочно|быстрее|быстро скажи|некогда|тороплюсь|спешу|коротко скажи|в двух словах|без воды',
        'en': r"\basap\b|hurry|in a rush|quickly|quick question|short answer|tl;?dr|no time",
        'ko': r'급해|빨리|바빠|간단히|짧게|시간 없',
        'ja': r'急いで|急ぎ|早く|時間がない|手短に|簡単に教えて',
    },
    'annoyed': {
        'ru': r'бесит|достало|задолбал|опять не работает|надоело|раздражает|взбесил',
        'en': r"annoying|pissed|fed up|sick of|so frustrat|drives me (crazy|nuts)|not working again",
        'ko': r'짜증|열받|빡치|지겨워|답답해',
        'ja': r'イライラ|むかつく|うんざり|腹が立|ムカつく',
    },
    # real grief or danger: no jokes at all
    'heavy': {
        'ru': r'умер|умерла|смерть|похорон|диагноз|онколог|суицид|покончить с собой|не хочу жить|развод|изнасил|операци',
        'en': r"passed away|funeral|died|diagnos|cancer|suicid|kill myself|don't want to live|divorce|abuse|surgery",
        'ko': r'돌아가셨|장례|사망|진단|암 |자살|죽고 싶|이혼|수술',
        'ja': r'亡くなっ|葬式|死にたい|診断|癌|自殺|離婚|手術',
    },
    # she says "you told me / I remember you...": a claim about him that the program checks against what she really knows
    'recall': {
        'ru': r'ты (же |уже |мне |как-то |ещё |еще )*(говорил|рассказывал|упоминал|писал|обещал)а?|(я )?помню,? (что |как )?ты|ты мне (говорил|рассказывал)',
        'en': r"you (once |already |just )?(told|said|mentioned|promised)|i remember (when |that )?you|you've (told|said|mentioned)",
        'ko': r'네가 (말했|얘기했|이야기했|그랬)|말했잖아|말했었|얘기했었',
        'ja': r'言ってた|言っていた|話してた|話していた|って言ったよね',
    },
    # the tone of his words: it moves her mood, hurts or pleases her (character.sense); first match in this order wins
    'tone_rude': {
        'ru': r'тупиц|тупая|дура\b|дурак|идиот|заткнись|заткни|ты бесишь|бесишь меня|ненавижу тебя|отстань от меня|ты бесполезн|ничтожеств',
        'en': r'fuck you|shut up|stupid|idiot|useless|i hate you',
        'ko': r'닥쳐|꺼져|너 싫어|네가 싫어|너 진짜 싫|(너|넌|네가) (진짜 )?(쓸모 ?없|한심)|저리 가',
        'ja': r'黙れ|消えろ|ばか野郎|バカ野郎|あっち行け|お前なんか|(お前|あなた)(が|の事が|のことが)?(大?嫌い|役立たず)|お前は役立たず',
    },
    'tone_sorry': {
        'ru': r'прости|извини|сорян|я виноват|мне жаль',
        'en': r'sorry|i apologi',
        'ko': r'미안|죄송|내 잘못|제 잘못|내가 잘못|사과할게|사과드려',
        'ja': r'ごめん|すみません|申し訳|悪かった|謝る',
    },
    'tone_thanks': {
        'ru': r'спасибо|благодарю|спс\b|молодец|умничка|ты лучшая|ты чудо|круто получилось',
        'en': r'thank|good job|you.?re (?:the best|great|amazing)',
        'ko': r'고마워|고맙|감사|땡큐|잘했어|너 최고|대단해',
        'ja': r'ありがと|感謝|サンキュ|よくやった|さすが|助かった',
    },
    'tone_sad': {
        'ru': r'грустно|грущу|мне печально|мне плохо|мне одиноко|одиноко|тоскую|так тяжело|мне тяжело|депресс|плачу|не хочу жить',
        'en': r'i feel (?:sad|lonely|down)|i.m (?:sad|lonely)',
        'ko': r'슬퍼|슬프|우울|외로워|외롭|쓸쓸|너무 힘들|눈물|울고 싶|죽고 싶|살기 싫',
        'ja': r'悲しい|寂しい|さみしい|つらい|辛い|落ち込|泣きたい|憂鬱|死にたい|孤独',
    },
    'tone_angry': {
        'ru': r'злюсь|бесит\b|достал[оаи]?\b|взбесил|раздражает|в ярости',
        'en': r'angry|furious|annoyed|pissed',
        'ko': r'화나|화가 나|짜증|열받|빡치|분노',
        'ja': r'腹が立|むかつく|ムカつく|イライラ|怒って|キレ|ふざけるな',
    },
    # a language-practice mode he switches on and off in words: she corrects his mistakes gently after her answer
    'tutor_on': {
        'ru': r'(поправляй|исправляй|проверяй) (мои|меня|мою)|(поправь|исправь) мои ошибки|я учу (корейск|японск|английск|русск)\w* ?(язык)?.{0,30}(поправ|исправ)|помоги (мне )?(с )?(практик|учить)\w* (корейск|японск|английск|русск)',
        'en': r'correct my (mistakes|grammar|english|korean|japanese|russian)|fix my (mistakes|grammar)|(i.m|i am) (learning|practic\w+) (english|korean|japanese|russian).{0,40}(correct|fix)|help me practi[cs]e',
        'ko': r'(내 )?(틀린|실수|문법).{0,6}(고쳐|바로잡아|알려)|(한국어|영어|일본어|러시아어).{0,10}(연습|공부).{0,20}(고쳐|도와)|(고쳐|교정해) ?줘',
        'ja': r'(間違い|ミス|文法).{0,6}(直して|訂正して|教えて)|(日本語|韓国語|英語|ロシア語).{0,12}(練習|勉強).{0,20}(直して|手伝って)|添削して',
    },
    'tutor_off': {
        'ru': r'(хватит|перестань|не надо|не нужно|больше не) (меня )?(поправлять|исправлять)|не поправляй|не исправляй|выключи (проверку|исправление)',
        'en': r'stop correcting|don.t correct|no more corrections|turn off (the )?(corrections|correcting)',
        'ko': r'그만 (고쳐|교정)|고쳐 ?주지 ?마|교정하지 ?마|안 고쳐도',
        'ja': r'直さなくて(いい|もいい)|訂正しないで|添削しないで|もう直さないで',
    },
    # being ill is not the same as being sad or tired: she asks about his health next time
    'tone_sick': {
        'ru': r'заболел|заболела|я болею|болею|простыл|простудил|у меня температура|высокая температура|температура (поднялась|под 3|3[7-9])|тошнит|болит (голова|горло|живот|зуб|спина)|голова болит|горло болит|живот болит|мне нездоровится|плохо себя чувствую',
        'en': r'i.m sick|i am sick|i feel sick|i.m ill|i am ill|i have a (fever|cold|headache|flu|migraine)|i caught a cold|my (head|throat|stomach|back) (hurts|aches)|feeling unwell|under the weather',
        'ko': r'아파|아프다|아픈데|몸살|감기|열이 (나|있)|두통|머리가 (아프|아파)|배탈|몸이 안 좋|컨디션이 안 좋|토할 것',
        'ja': r'具合が悪い|ぐあいがわるい|体調(が)?(悪|わる)|熱が(ある|出)|風邪|頭が痛|お腹が痛|喉が痛|吐き気|気持ち悪い',
    },
    'tone_tired': {
        'ru': r'устал|вымотал|не выспал|спать хочу|засыпаю',
        'en': r'tired|exhausted|sleepy',
        'ko': r'피곤|지쳤|졸려|잠 와|못 잤|기운 없|녹초',
        'ja': r'疲れ|眠い|ねむい|寝不足|くたくた|へとへと|だるい',
    },
    'tone_happy': {
        'ru': r'ура\b|класс\b|обожаю|счастлив|я рад\b|я рада\b|получилось|отлично',
        'en': r'yay|awesome|so happy|i.m happy',
        'ko': r'행복|기뻐|신나|너무 좋아|야호|해냈|합격|성공했|대박',
        'ja': r'嬉しい|うれしい|幸せ|やった|楽しい|できた|受かった|合格',
    },
    # leaving or going to sleep: a short farewell is answered like family does, not with a new topic (a short message only: see convo.farewell)
    'selfask': {   # he asks about her own nature or feelings: alive, real, an AI, does she love or miss him, is she lonely
        'ru': r'ты (?:что |правда |вообще |на самом деле )?(?:живая|настоящая|человек|робот|бот|нейросеть|программа|ии)\b|ты (?:(?:правда|вообще|реально|на самом деле) )?(?:меня )?(?:любишь|скучаешь|скучала)|'
              r'тебе (?:бывает )?(?:одиноко|грустно|страшно|больно|скучно)|ты (?:(?:правда|вообще|на самом деле|реально) )?(?:(?:хоть )?что-то )?(?:чувствуешь|переживаешь|осознаёшь|осознаешь)|у тебя есть (?:чувства|душа|сознание|эмоции)',
        'en': r"are you (?:really |actually )?(?:real|alive|human|a robot|an? ai|a bot|conscious|sentient)|do you (?:really |actually )?(?:love|miss|feel|care about) (?:me|anything|things)|"
              r"do you have (?:feelings|a soul|emotions|consciousness)|are you (?:ever )?(?:lonely|sad|scared)|do you get (?:lonely|sad|scared)",
        'ko': r'너(?:는|도)? ?(?:진짜 )?(?:살아 ?있|진짜|사람이|로봇|AI|인공지능)|(?:나를|날) (?:사랑|좋아|보고 ?싶)|너 ?(?:외로워|외롭|슬퍼|무서워)|(?:감정|마음|영혼|의식)(?:이|은)? ?있어',
        'ja': r'あなたは(?:本当に)?(?:生きて|本物|人間|ロボット|AI)|(?:私|僕|俺)のこと(?:を)?(?:好き|愛して|寂しい)|(?:寂しい|怖い|悲しい)(?:の|ですか|\?|？)|(?:感情|心|魂|意識)(?:は|が)?(?:ある|あるの)',
    },
    'compliment': {   # he praises her herself (not a thank-you): smart, nice, funny, pretty, the best
        'ru': r'ты (?:такая |очень |правда |просто |всё-таки |всегда )*(?:умная|умничка|классная|красивая|милая|прикольная|смешная|замечательная|лучшая|добрая|талантливая|крутая|чудо|прелесть|золото)|'
              r'мне (?:очень )?(?:нравится|повезло) (?:с тобой|говорить с тобой|с тобой общаться)|рад(?:а)?,? что ты (?:есть|у меня)',
        'en': r"you(?:'re| are) (?:so |really |such an? |very |just |always )*(?:smart|clever|cool|funny|sweet|kind|great|amazing|awesome|beautiful|wonderful|the best|talented|lovely|a gem)|"
              r"i (?:really )?(?:like|love|enjoy) talking (?:to|with) you|glad (?:that )?(?:you(?:'re| are)|i have you)",
        'ko': r'너(?:는|무|랑)? ?(?:정말 |진짜 |너무 |참 )?(?:똑똑해|귀여워|착해|멋져|예뻐|재밌어|웃겨|최고야|대단해|천재|고마운 존재)|너(?:랑|와) (?:얘기|이야기|대화)(?:하는 게|하면) (?:좋아|즐거워)|네가 있어서 (?:좋아|다행)',
        'ja': r'(?:あなた|君|きみ)(?:は|って)(?:本当に|とても|すごく|ほんと)?(?:賢い|かわいい|可愛い|優しい|面白い|素敵|最高|すごい|天才|きれい)|(?:あなた|君|きみ)と(?:話すの|話してる(?:と)?)(?:が)?(?:好き|楽しい)|(?:あなた|君)がいてくれて(?:よかった|嬉しい)',
    },
    'bye': {
        'ru': r'спокойной ночи|доброй ночи|сладких снов|споки\b|спокиньки|пойду спать|иду спать|я спать|ложусь спать|пора спать|до завтра|до встречи|до свидания|мне пора|я побежал|побегу|увидимся|^\W*пока\W*$|^\W*бай\W*$',
        'en': r'good ?night|sweet dreams|(going|heading|off) to (bed|sleep)|gotta go|got to go|i have to go|i.ll go now|talk (to you )?later|see you (later|tomorrow|soon)|^\W*(bye|goodbye|cya|bye bye)\W*$',
        'ko': r'잘 ?자|자러 (갈|가)|자야겠|굿나잇|안녕히 (계세|주무)|가볼게|갈게|먼저 갈게|내일 봐|다음에 봐|나중에 봐|이만 (갈|가)|바이바이|^\W*바이\W*$',
        'ja': r'おやすみ|寝る(ね|よ|わ|か)|寝ます|寝るから|またね|じゃあね|じゃね|バイバイ|行ってきます|落ちる(ね|わ)|また明日|失礼します|そろそろ(行く|寝る|失礼)',
    },
    # arriving: a good morning or "I am back" is answered at home, not by an assistant
    'hello': {
        'ru': r'доброе утро|добрый день|добрый вечер|доброй ночи|^\W*(привет|здравствуй|здравствуйте|хай|приветик|салют)\b|я вернул(ся|ась)|я дома|вот и я|я тут\b|я пришёл|я пришел',
        'en': r'good (morning|evening|afternoon)|^\W*(hello|hi|hey|hiya|yo|morning)\b|i.m back|i am back|i.m home|i.m here',
        'ko': r'좋은 아침|굿모닝|^\W*(안녕|하이|헬로)|나 왔어|왔어\b|돌아왔|다녀왔|나 왔다',
        'ja': r'おはよう|こんにちは|こんばんは|ただいま|戻った|戻ったよ|帰ってきた|^\W*(やあ|ハロー|よう)',
    },
    # assistant clichés she must never open or close with: cut from her spoken sentences
    'cliche_opener': {
        'ru': r'конечно|разумеется|безусловно|отличный вопрос|хороший вопрос|интересный вопрос|спасибо за (вопрос|твой вопрос)',
        'en': r'of course|certainly|absolutely|sure thing|great question|good question|interesting question|thanks for (asking|your question)',
        'ko': r'물론이죠|물론이에요|물론입니다|좋은 질문(이에요|입니다)?|흥미로운 질문(이네요)?|질문 감사(해요|합니다)?',
        'ja': r'もちろん(です)?|かしこまりました|承知(いたしました|しました)|いい質問(ですね)?|良い質問(ですね)?|質問ありがとう(ございます)?',
    },
    'cliche_sentence': {
        'ru': r'чем (могу|могла бы) (тебе |вам )?помочь|если у (тебя|вас) (есть|появятся) (ещё )?(вопросы|идеи)|надеюсь,? (это|я) (поможет|помогла)|я (здесь|тут),? чтобы|как (ии|искусственный интеллект|языковая модель)\b|не стесняйся (спрашивать|обращаться)|обращайся(,? если)?|давай разберёмся|важно отметить|стоит отметить|в заключение|подводя итог|надеюсь,? тебе (понравится|помогло)|дай знать,? если|рада (была )?помочь|буду рада помочь|приношу (свои )?извинения|прошу прощения за (путаницу|недоразумение|ошибку)|извини за (путаницу|недоразумение)',
        'en': r'how can i (help|assist)( you)?|let me know if|i hope (this|that) helps|feel free to|as an ai|as a language model|i.m here to|don.t hesitate to|i apologi[sz]e for the (confusion|inconvenience)|happy to help|in conclusion|it.s important to note|it is worth noting|please note that',
        'ko': r'무엇을 도와|도움이 (필요하|되었)|도움이 되었(기를|길)|궁금한 (점|것)이 (있으|있다)면|언제든지 (물어|말씀)|AI로서|인공지능으로서|언어 모델로서|혼란을 드려|불편을 드려|결론적으로|참고로 말씀',
        'ja': r'何かお手伝い|お役に立てれば|お役に立てて|ご質問があれば|お気軽に|AIとして|言語モデルとして|混乱を(招|させ)|ご不便をおかけ|結論として|ご参考まで',
    },
}


TONE_ORDER = ('rude', 'sorry', 'thanks', 'sad', 'angry', 'sick', 'tired', 'happy')


def fragment(concept):
    return '|'.join(WORDS[concept][lang] for lang in LANGS + ('any',) if lang in WORDS[concept])


def rx(concept):
    return re.compile('(?i)(' + fragment(concept) + ')')


class Fresh:
    """Looks like a thing that goes stale: a topic word (price, weather, news, version) on its own, or a time word together with a
    question word, unless the question is about her or him ("what are you doing now")."""
    strong = rx('fresh')
    time = rx('fresh_time')
    wh = rx('fresh_wh')
    chat = rx('fresh_chat')

    def search(self, text):
        text = str(text or '')
        if self.strong.search(text):
            return True
        return bool(self.time.search(text) and self.wh.search(text) and not self.chat.search(text))


def covered(concept, phrases):
    """Which phrases the concept misses: used by the tests (a phrase per language)."""
    pattern = rx(concept)
    return [p for p in phrases if not pattern.search(p)]
