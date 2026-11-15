"""Re-tunes MIN_SIM and MARGIN of luna/core/feeling.py: 52 labelled phrases (none of them are the examples in feeling.py) are scored with the real
embedding model, and every pair of thresholds is tried. Needs Ollama running with the model. Usage:  python tools/feeling_calibrate.py
Pick the pair with no false alarms and no wrong tones that finds the most real ones. Nothing leaves the computer."""
import itertools
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from luna.core import feeling, memory_store  # noqa: E402

DATA = {
    'sad': ['честно, всё какое-то серое', 'мне так пусто сегодня', 'опять ночь без сна и мысли о плохом, ничего не хочется', 'it has been a rough week',
            'I just feel empty lately', 'nothing makes me happy anymore', '요즘 너무 우울해', '最近ほんとうに寂しい'],
    'angry': ['меня это просто бесит', 'как же я зол на него', 'I am so mad at my boss right now', 'this is infuriating', '진짜 화난다', 'もう本当に腹が立つ'],
    'sick': ['у меня жутко болит горло и температура', 'кажется, я простыл', 'I have a splitting headache and I am freezing', 'I think I am coming down with the flu',
             '감기 걸린 것 같아', '熱があって頭が痛い'],
    'tired': ['я вообще без сил после работы', 'засыпаю на ходу', 'I am completely wiped out', 'I could sleep for a week', '너무 피곤해', 'もう限界で眠い'],
    'happy': ['мне предложили работу мечты!', 'сегодня просто чудесный день', 'I finally did it, they said yes!', 'best day ever', '드디어 합격했어!', 'やっと成功した！'],
    'thanks': ['ты меня так выручила, спасибо', 'благодарю, очень помогло', 'thanks, that really saved my evening', 'you are the best, thank you', '진짜 고마워', '助かった、ありがとう'],
    '': ['открой калькулятор', 'какой сегодня курс доллара', 'расскажи про устройство самолёта', 'what is the capital of Australia', 'let us plan the project for next week',
         'summarize this article', 'сколько будет двенадцать умножить на семь', 'напомни завтра про встречу', '내일 일정 알려줘', '今日のニュースを教えて',
         'как дела?', 'привет', 'давай поговорим о кино', 'what do you think about jazz'],
}

memory_store.set_embedder(*memory_store.ollama_embedder(model='nomic-embed-text'))
feeling.warm('ollama:nomic-embed-text')
for _ in range(900):
    if 'ollama:nomic-embed-text' in feeling._pool:
        break
    if feeling._failed[0]:
        sys.exit('model does not answer')
    time.sleep(0.1)

rows = []
for want, phrases in DATA.items():
    for ph in phrases:
        sc = feeling.scores(ph)
        rows.append((want, ph, sc))
print('scored', len(rows), 'phrases')


def decide(sc, min_sim, margin):
    tones = {t: v for t, v in sc.items() if t}
    best = max(tones, key=tones.get)
    return best if tones[best] >= min_sim and tones[best] - sc[''] >= margin else ''


def evaluate(min_sim, margin):
    tp = wrong = missed = fp = tn = 0
    for want, _ph, sc in rows:
        got = decide(sc, min_sim, margin)
        if want:
            if got == want: tp += 1
            elif got: wrong += 1
            else: missed += 1
        else:
            if got: fp += 1
            else: tn += 1
    return tp, wrong, missed, fp, tn

print('current MIN_SIM=%.2f MARGIN=%.2f ->' % (feeling.MIN_SIM, feeling.MARGIN), 'right=%d wrongtone=%d missed=%d falsealarm=%d ok-everyday=%d' % evaluate(feeling.MIN_SIM, feeling.MARGIN))
print('--- sweep (no false alarms wanted first, then most right)')
res = []
for ms, mg in itertools.product([x / 100 for x in range(20, 71, 5)], [x / 100 for x in range(0, 21, 2)]):
    tp, wrong, missed, fp, tn = evaluate(ms, mg)
    res.append((fp, wrong, -tp, ms, mg, tp, missed))
res.sort()
for r in res[:12]:
    print('MIN_SIM=%.2f MARGIN=%.2f  right=%d missed=%d wrongtone=%d falsealarm=%d' % (r[3], r[4], r[5], r[6], r[1], r[0]))
print('--- raw scores of a few')
for want, ph, sc in rows[:3] + rows[24:27] + rows[-3:]:
    print(want or 'everyday', '|', ph, '|', ' '.join('%s=%.2f' % (t or 'e', v) for t, v in sorted(sc.items(), key=lambda kv: -kv[1])[:3]))
