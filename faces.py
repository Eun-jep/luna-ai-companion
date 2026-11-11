"""The face of her model beyond the nine basic moods: the model's own expression files (tears, blush, heart eyes, white eyes, panic, ...).
The page reads which ones the loaded model has and sends only their names; this module knows what each one means and tells her which she has and when each
fits. She uses them freely, there is no rate limit. The page maps file names to these names (web/avatar.js FX_KEYWORDS)."""

# name: what it looks like and when it fits (she is told only about the ones her model has)
FX = {
    'tears': 'слёзы на глазах: растрогалась, грустно, обидно до слёз, тронута',
    'blush': 'румянец: смущение, комплимент, неловко-приятно',
    'hearts': 'глаза-сердечки: умиление, обожание, что-то очень милое, любовь',
    'stars': 'глаза-звёзды: восторг, мечтает, «вау, хочу!»',
    'anger': 'злое лицо: возмущение, по-настоящему рассердилась',
    'shock': 'шок: потрясена, не ожидала такого',
    'confused': 'вопросительное лицо: не поняла, озадачена',
    'gloom': 'затемнённое лицо: мрачная обида, жуть, разочарование, «да ну тебя»',
    'eyeroll': 'белые глаза, закатить глаза: скепсис, «ну-ну», отвращение, плохая шутка',
    'panic': 'паника: испуг, ужас, «ой-ой-ой»',
    'tongue': 'язык наружу: дурачится, дразнит, шутит',
    'smirk': 'ухмылка набок: хитрость, самодовольство, подколка',
    'money': 'глаза-монеты: шутливая жадность, «это дорого!»',
    'squint': 'прищуренная улыбка: довольна, мурлычет, мягкая радость',
    'sweat': 'линии неловкости: «ой», неловкая пауза, стыдно за шутку',
}
# the model's own movements (loose .motion3.json files): [mo:name]
MOTIONS = {
    'wave': 'помахать рукой: привет, пока, прощание',
    'wink': 'кокетливый взгляд, подмигивание: флирт, шутка',
    'curious': 'любопытство: заинтересовалась, «о, расскажи»',
    'headshake': 'покачать головой: нет, не согласна, «ай-ай-ай»',
    'sleepy': 'клевать носом: сонная, устала, уже поздно',
    'photo': 'сфотографировать: «сфоткаю!», запомнить момент, шутка',
    'wings': 'взмах крыльев: радость, лёгкость, торжество',
    'glasses': 'поправить очки: серьёзный момент, «давай по делу»',
}
MAX_LISTED = 15


def known(names):
    """The effect names that came from the page, cleaned: only ones this module knows, in a stable order, each once."""
    if not isinstance(names, (list, tuple)):
        return []
    seen = {n for n in names if isinstance(n, str) and n in FX}
    return [n for n in FX if n in seen][:MAX_LISTED]


def known_motions(names):
    if not isinstance(names, (list, tuple)):
        return []
    seen = {n for n in names if isinstance(n, str) and n in MOTIONS}
    return [n for n in MOTIONS if n in seen][:MAX_LISTED]


def hint(available, motions=()):
    """Next to his message: which special faces and movements her model has and the rule of using them. '' when the model has none."""
    available, motions = known(available), known_motions(motions)
    if not available and not motions:
        return ''
    lines = '; '.join(['[fx:%s] — %s' % (n, FX[n]) for n in available] + ['[mo:%s] (движение) — %s' % (n, MOTIONS[n]) for n in motions])
    return (' [У твоей модели есть особые выражения лица и движения, ты можешь вставить одно в реплику, как эмоцию в тексте: %s. Это твоё лицо и твои движения, пользуйся ими свободно, когда '
            'чувствуешь (смущение, обида, отвращение, испуг, умиление, шутка, просто настроение), как делает живой человек, и не по счёту, а по поводу. Отвращение и скепсис можно показать [disgusted] и [fx:eyeroll], испуг: [scared] и [fx:panic].]' % lines)
