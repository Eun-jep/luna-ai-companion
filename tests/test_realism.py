"""Plain human talk, enforced on the host (convo.py): no markup or customer-service phrases in speech, small messages get small answers."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.core import convo
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

ok('bullet mark is removed', convo.polish('- Первое, что приходит в голову') == 'Первое, что приходит в голову')
ok('heading mark is removed', convo.polish('## Итак') == 'Итак')
ok('numbered mark is removed', convo.polish('1. Сначала чай') == 'Сначала чай')
ok('bold is unwrapped', convo.polish('Это **очень** важно') == 'Это очень важно')
ok('code stays as it is', convo.polish('```py\n- x\n```') == '```py\n- x\n```')
ok('directions in brackets stay', convo.polish('[smile] - Привет').startswith('[smile]') and 'Привет' in convo.polish('[smile] - Привет'))
ok('a new cliché sentence goes', convo.polish('Важно отметить, что это сложно.') == '' and convo.polish('Дай знать, если что.') == '')
ok('an old cliché sentence still goes', convo.polish('Чем могу помочь?') == '')
ok('plain speech is untouched', convo.polish('Ну и денёк у тебя вышел.') == 'Ну и денёк у тебя вышел.')

ok('no cap on her answers: she is free to say more or less', not hasattr(convo, 'Cap'))

ok('night is quiet', 'ночь' in convo.daypart(2) and 'ночь' in convo.daypart(23))
ok('morning', 'утро' in convo.daypart(7))
ok('evening', 'вечер' in convo.daypart(21))
ok('day: nothing', convo.daypart(14) == '')
h = convo.hints([], 'расскажи как прошёл твой день сегодня вообще', pick=lambda s: list(s)[0], hour=2)
ok('hints carry the hour and a living rhythm', 'ночь' in h and 'живой' in h or 'живая' in h or 'ритм' in h)
h = convo.hints([], 'расскажи как прошёл твой день сегодня вообще', hour=14)
ok('no pick: no random lines, no hour at midday', 'ритм' not in h and 'ночь' not in h)

ok('callback: nothing known, nothing said', convo.callback_hint([], lambda s: list(s)[0]) == '')
ok('callback: sometimes, with the fact', 'любит чай' in convo.callback_hint(['любит чай'], lambda s: list(s)[0]))
ok('callback: not every time', convo.callback_hint(['любит чай'], lambda s: list(s)[-1]) == '')
h = convo.hints([], 'расскажи как прошёл твой день сегодня вообще', pick=lambda s: list(s)[0], hour=14, facts=['любит чай'])
ok('hints carry the callback', 'любит чай' in h)
h = convo.hints([], 'ага', pick=lambda s: list(s)[0], hour=14, facts=['любит чай'])
ok('a nod gets no callback', 'любит чай' not in h)

sad = [{'role': 'user', 'content': 'мне сегодня очень грустно и я устал от всего этого'}, {'role': 'assistant', 'content': 'Я рядом.'}]
ok('a curt answer after something heavy: she does not take it at face value', 'отмашка' in convo.hints(sad, 'норм', pick=None, hour=14))
ok('a curt answer in a light talk: no such hint', 'отмашка' not in convo.hints([{'role': 'user', 'content': 'привет как дела у тебя сегодня'}], 'норм', pick=None, hour=14))

hang = [{'role': 'assistant', 'content': 'Хорошо. А что ты любишь есть?'}, {'role': 'user', 'content': 'а ты что любишь?'}, {'role': 'assistant', 'content': 'Я люблю гречку.'}]
ok('open question found', convo.open_question(hang) == 'А что ты любишь есть?')
ok('answered question: none', convo.open_question([{'role': 'assistant', 'content': 'Что ел?'}, {'role': 'user', 'content': 'кашу'}, {'role': 'assistant', 'content': 'Ясно.'}]) == '')
ok('no history: none', convo.open_question([]) == '')
ok('hint brings it back', 'повис' in convo.hints(hang, 'интересно, расскажи ещё что-нибудь', hour=14))

rep = ['Гречка всегда спасает, гречка с маслом особенно.', 'Люблю гречку, особенно гречка вкусная с маслом.', 'Опять гречка, масло и гречка.']
ok('worn words found', len(convo.worn_words(rep)) >= 3 and 'гречка' in convo.worn_words(rep))
ok('varied replies: none', convo.worn_words(['Привет, как дела.', 'Сегодня дождь за окном.', 'Завтра выходной наконец.']) == [])
ok('hint about circling', 'крутишься' in convo.hints([{'role': 'assistant', 'content': r} for r in rep], 'расскажи ещё что-нибудь', hour=14))

many = [{'role': 'assistant', 'content': r} for r in rep]
h = convo.hints(many, 'расскажи ещё что-нибудь интересное про свой день', pick=lambda s: list(s)[0], hour=2, facts=['любит чай'])
ok('soft hints are limited, the orders stay', h.count(' [') <= convo.MAX_SOFT + 2 and 'ночь' in h)
h = convo.hints(many + [{'role': 'assistant', 'content': 'Ну вот так.'}], 'расскажи ещё что-нибудь интересное про свой день', pick=lambda s: list(s)[0], hour=2, facts=['любит чай'])
ok('habit-breaking hints win over colour', 'Недавно ты начинала' in h or 'крутишься' in h)

ok('doubled marks collapse', convo.polish('Ну ты даёшь!!! Серьёзно??') == 'Ну ты даёшь! Серьёзно?')
loud = [{'role': 'assistant', 'content': t} for t in ('Привет!', 'Круто!', 'Здорово!')]
ok('a run of exclamations is calmed down', 'без «!»' in convo.hints(loud, 'расскажи ещё что-нибудь интересное', hour=14))

ok('thanks: taken simply', 'Он благодарит' in convo.hints([], 'спасибо, ты очень помогла', hour=14))
ok('laughter: shared', 'Он смеётся' in convo.hints([], 'ахах, ну ты даёшь, это смешно', hour=14))
ok('no thanks, no hint', 'благодарит' not in convo.hints([], 'расскажи про космос', hour=14))

ok('a correction: taken simply', 'ошиблась' in convo.hints([], 'нет, ты ошиблась, это не так работает', hour=14))
ok('no correction, no hint', 'ошиблась' not in convo.hints([], 'расскажи про космос', hour=14))
ok('apology cliché goes', convo.polish('Приношу извинения за путаницу.') == '' and convo.polish('Прошу прощения за путаницу.') == '')
