"""Questions about her own nature and feelings (convo.SELFASK) in ru/en/ko/ja: an honest, non-canned hint; silence on ordinary talk."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import convo
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

asks = ['ты живая?', 'ты настоящая?', 'ты правда меня любишь?', 'ты скучаешь, когда меня нет?', 'тебе бывает одиноко?', 'у тебя есть чувства?', 'ты робот?', 'ты вообще что-то чувствуешь',
        'are you real?', 'are you an AI?', 'do you love me?', 'do you miss me when I leave?', 'do you have feelings?', 'are you lonely?', 'are you alive',
        '너 진짜 살아있어?', '너 사람이야?', '나를 사랑해?', '너 외로워?', '감정이 있어?', 'あなたは本当に生きてるの', '私のこと好き?', '寂しいの？', '感情はあるの', 'あなたはAIですか']
for ph in asks:
    h = str(convo.hints([], ph))
    ok('self question: ' + ph, 'спрашивает о тебе самой' in h and 'не как справка' in h)
for ph in ['ты поняла задачу?', 'ты где?', 'ты видела мой файл?', 'как дела?', 'расскажи про живую природу', 'do you know the way?', 'are you coming tonight?', 'I love this song',
           '너 어디야?', '日本に行きたい', 'у меня есть чувство, что будет дождь', 'мне одиноко', 'у меня нет души к этой работе']:
    ok('ordinary talk has no self-question hint: ' + ph, 'спрашивает о тебе самой' not in str(convo.hints([], ph)))
h = str(convo.hints([], 'ты живая?'))
ok('hint forbids the canned refusal and the big promises', 'всего лишь ИИ' in h and 'громких заверений' in h)
ok('hint keeps honesty about being a program', 'ты программа' in h)
