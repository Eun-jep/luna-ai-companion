"""One turn of the conversation: the chat engine (streams NDJSON events). Everything it needs from app.py that tests replace is reached through _app()."""
from luna import security
from luna.core import audit
from luna.core import character
from luna.core import convo
from luna.core import faces
from luna.core import recall
from luna.core import replyfeel
from luna.core.character import (HISTORY, MEMORY, MEMORY_EVERY, REFLECT_EVERY, NOTE, TAG_RE, save_memory,
                       mood_now, mood_from_script, update_memory, reflect)
from luna.core.models import list_models, parameter_labels   # noqa: F401  (the Live2D models on disk; re-exported for the tests)
from luna.core.prompts import (ACTIONS_FILE, WORK_OFF, library_line, load_actions, DOUBT, LANGS, LAST_USER, NOOK_RULES, PRESENCE_RULES, PROTOCOL, SCENES, SUMMARY, WEEKDAYS, system_prompt, time_context)   # noqa: F401
from luna.core.script import (BOUNDARY_RE, clean_script, CYRILLIC_RE, EMOJI_RE, EMOTIONS, FOREIGN_RE, GESTURES, HANGUL_RE, JA_RE, JA_VOICE, LOOK_TARGETS, MAX_MESSAGE, MAX_STORED, MIN_CHUNK, NATIVE_VOICES, parse_plan, parse_script, pick_voice, PLAN_MAX, PLAN_MIN, PLAN_STEP, pull_code, split_ready, tts_clean, TTS_VOICE, VALID_TAGS)   # noqa: F401  (pure helpers: stage directions, voice choice, sentence cutting; some are re-exported for the tests)
from luna.core.session import S
from luna.dev import codescan
from luna.dev import devtools
from luna.dev import engines
from luna.dev import envdiag
from luna.dev import gameerrors
from luna.dev import gitdiff
from luna.dev import godot_bridge
from luna.dev import logs
from luna.dev import sqlcheck
from luna.dev import sqlrun
from luna.dev import testgen
from luna.dev import traces
from luna.dev import unity_bridge
from luna.dev import unreal_bridge
from luna.hands import agent
from luna.hands import codeedit
from luna.hands import control
from luna.hands import docfiles
from luna.hands import netsearch
from luna.hands import nook
from luna.hands import office
from luna.hands import projects
from luna.hands import runner
from luna.hands import studio
from luna.hands.agent import ACT_RE
from luna.senses import hearing
from luna.senses import media
from luna.skills import abilities
from luna.skills import agenda
from luna.skills import chance
from luna.skills import dates
from luna.skills import exact
from luna.skills import habits
from luna.skills import lists
from luna.skills import manners
from luna.skills import mathtalk
from luna.skills import money
from luna.skills import pcstate
from luna.skills import recipes
from luna.skills import reminders
from luna.skills import standup
from luna.skills import stream
import random
import threading
import time
import urllib.error
import urllib.request
from luna.server.appref import _app



def chat_turn(data):
    """One conversation turn as a stream of events: {'answer', 'script'} per sentence, then {'done', 'mood'}.
    Sentences are cut from the model's text as it is written, so speech can start before the reply is finished."""
    S.agent = isinstance(data, dict) and data.get('agent') is True and not stream.ON   # no hands on the stream
    S.work = S.agent and data.get('work') is True
    S.unreal = S.work   # Unreal is part of her hands: every operation still waits for the creator's press
    S.control = S.agent and data.get('control') is True
    S.camera_on = isinstance(data, dict) and data.get('camera') is True
    S.presence = isinstance(data, dict) and data.get('presence') is True and not stream.ON
    S.ui_lang = data.get('lang') if isinstance(data, dict) and data.get('lang') in LANGS else 'en'
    if S.last_lang not in (None, S.ui_lang):   # the language was switched: old replies in the other language would pull her back
        del HISTORY[:-2]
    S.last_lang = S.ui_lang
    if isinstance(data, dict) and data.get('scene') in SCENES:
        S.scene = data['scene']
    initiative = data.get('initiative') if isinstance(data, dict) else None
    if initiative:   # she speaks first: a service note instead of a user message
        if initiative not in _app().INITIATIVES or (initiative.startswith('stream') and not stream.ON) or (stream.ON and initiative in ('screen', 'media', 'care', 'late', 'scene', 'return', 'remind')):
            raise ValueError('initiative')
        text = NOTE + _app().INITIATIVES[initiative]
        if initiative == 'stream':   # a batch of chat messages and events
            text = NOTE + stream.note(stream.take())
            if text == NOTE:
                raise ValueError('initiative')
        if initiative == 'idle' and stream.ON:   # dead air on the stream
            text = NOTE + random.choice(stream.DEAD_AIR)
        if initiative == 'greet':   # something to care about (a date, a promise, a late night) joins the greeting
            text += ''.join(' ' + c for c in [character.care_note()] if c)
        if initiative == 'media':   # she noticed what he is watching or listening to (the page sends only a media window title)
            heard = hearing.fresh()
            info = media.detect(data.get('window')) or media.from_sound(heard)   # a known title first, else just what she hears
            if not info or not media.allow(info):   # not a player, too soon, or already discussed: she keeps quiet
                raise ValueError('initiative')
            text = NOTE + media.prompt(info, heard=heard)
        if initiative == 'care':   # woken by a date she remembers (see /care/due)
            text = NOTE + character.care_note(dated_only=True)
            if text == NOTE:
                raise ValueError('initiative')
        if initiative == 'remind':   # the time he asked for has come
            ripe = character.take_reminders()
            if not ripe:
                raise ValueError('initiative')
            save_memory()
            text = NOTE + ('Время, на которое он просил напомнить, пришло: %s. Скажи ему об этом сама, коротко и тепло, как близкий человек, '
                           'одной-двумя фразами, без «напоминаю вам».' % '; '.join('«%s»' % (e['text'] or 'он не уточнил, о чём') for e in ripe))
        if initiative == 'scene':
            text = text % SCENES[S.scene]
        elif initiative == 'idle' and S.presence:
            last = HISTORY[-1] if HISTORY else None
            asked = last and last['role'] == 'assistant' and convo.ends_question(TAG_RE.sub('', last['content']))
            text = NOTE + (_app().NUDGE if asked else convo.idle_prompt(SUMMARY['text'], _app().IDLE_PRESENCE, random.choice, character.MEMORY['user'], mood=character.mood_now(), views=['%s: %s' % (o['topic'], o['view']) for o in character.MEMORY['opinions'][-6:]]))
            if not asked and random.random() < _app().IDLE_FOLLOW:   # a promise or a date of his that is worth a word, not only at the greeting
                follow = character.care_note()
                if follow:
                    text = NOTE + follow
    else:
        text = data.get('message', '') if isinstance(data, dict) else ''
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= MAX_MESSAGE:
        raise ValueError('message')
    user = {'role': 'user', 'content': text.strip()}
    # A screenshot comes with her own glance ('screen') or with a user message about the screen ("видишь?").
    image = data.get('image') if isinstance(data, dict) and initiative in (None, 'screen') else None
    if (initiative == 'screen' or image is not None) and not (
            isinstance(image, str) and image.startswith('data:image/jpeg;base64,') and len(image) <= _app().MAX_IMAGE):
        raise ValueError('image')
    # The screenshot goes to the model for this one turn only; the history keeps just the text.
    hint = ''
    if image:
        title = data.get('window')
        if isinstance(title, str) and title.strip():
            hint = ' [Активное окно: «%s».]' % ' '.join(title.split())[:150]
        if not initiative:
            hint = (' [К сообщению приложен скриншот его экрана прямо сейчас: посмотри на него и ответь по делу, '
                    'без отговорок, что не видишь экран. Сначала пойми, что на экране (редактор кода, движок, игра, браузер, ошибка), '
                    'и опирайся на то, что видно: читай текст ошибок и строк кода точно, называй панели и кнопки так, как они подписаны. '
                    'Если мелкое не разобрать, так и скажи и попроси прислать текст или файл (можно командой [read:...]), а не угадывай. '
                    'Пароли, ключи и чужую переписку не читай вслух.]') + hint
    elif not initiative and data.get('screen_off') in _app().SCREEN_OFF_HINTS:
        hint = _app().SCREEN_OFF_HINTS[data['screen_off']]
    if stream.ON and not initiative:   # he speaks into the stream: she answers the host first
        hint += ' [Это говорит хост, создатель, в эфире: ответь ему, ты на стриме.]'
    if S.work and not initiative:   # a stack trace or a test run in his message (or in a command output): the program reads it first
        diag = traces.analyze(text)
        if diag:
            hint += ' [' + diag + ']'
        for reader in (logs.analyze, sqlcheck.analyze, testgen.analyze):   # a service log, SQL, code he wants tests for: read by the program, nothing is run
            note = reader(text)
            if note:
                hint += ' [' + note + ']'
    if S.presence and not initiative:   # how a real interlocutor would answer this very message
        now = time.time()
        gap = now - LAST_USER['t'] if LAST_USER['t'] else 0
        LAST_USER['t'] = now
        convo.observe(text)
        cut = data.get('cut') if isinstance(data.get('cut'), str) else ''
        hint += convo.hints(HISTORY, text, gap, cut[:150], random.choice, facts=character.MEMORY['user'], mood=character.mood_now(), held=bool(character.opinions_for(text)), web=S.agent)
    if not initiative and isinstance(data.get('media'), str):   # "how do you like it?": she knows what is playing
        info = media.detect(data['media'])
        if info:
            hint += media.prompt(info, first=False, heard=hearing.fresh())
    if not initiative:
        hint += _app().ears_hint(text, data) + (character.learned_hint(text) if not data.get('web') else '') + character.lessons_hint(text)
        if reminders.manage_kind(text):   # "what reminders do I have" / "cancel the reminder about tea": done by the program, on his words
            hint += reminders.manage(text, character.MEMORY['reminders'])
            save_memory()
        parsed = reminders.parse(text) if not reminders.manage_kind(text) else None
        if parsed and character.add_reminder(*parsed):   # he asked to be reminded: the program keeps it and she speaks first when it is time
            save_memory()
            hint += (' [Программа поставила напоминание на %s%s. Скажи ему коротко, что напомнишь в это время (это сработает, пока Луна открыта).]'
                     % (reminders.clock(parsed[0]), ' про «%s»' % parsed[1] if parsed[1] else ''))
        if not (isinstance(data, dict) and data.get('web')):   # his shopping / to-do list: changed or read at once because he asked in words (never after web text)
            hint += lists.handle(text)
            hint += agenda.hint(text, character.MEMORY['reminders'], character.MEMORY['moments'], lists.load()['todo'], habits_left=habits.pending())   # "what is on today": the real plan, not an invented one
            hint += mathtalk.hint(text)   # a sum, a percentage, a root or a unit conversion said in words: counted exactly by the program
            hint += dates.handle(text)   # calendar counting ("how many days until", "what date in 100 days", age): the program knows today and counts exactly
            hint += habits.handle(text)   # habits and streaks: counted by the program, she only retells
            hint += manners.handle(text) or manners.standing()   # his own requests about her manner ("shorter", "no jokes", "call me X"): kept if standing, reminded every turn
            hint += pcstate.hint(text, S.agent)   # "why is my pc slow / how much disk": read-only numbers from his computer, only with the Actions switch on
            hint += abilities.hint(text, S.agent, S.work)   # "what can you do": a true list for this moment (which switches are on), no boasting and no forgetting
            hint += gameerrors.hint(text)   # an engine error pasted in: recognised by its fixed text, usual cause and first check from a table
            hint += recipes.hint(text)   # "build a platformer in Godot": a checked recipe, three operations per reply (the cap), each still waits for his press
            hint += engines.analysis_hint(text) or engines.mention_hint(text)   # "analyze my project" (read-only look at his folder) or facts about an engine he asks about
            hint += chance.hint(text)   # a coin, dice, a random number, "pick one": thrown by the program, not guessed by the model
            hint += money.hint(text, S.agent)   # an exchange rate on request: from the internet, so only with the Actions switch on
        if not (isinstance(data, dict) and data.get('web')):   # the practice mode is switched only by his own words, never by text from the internet
            hint += character.tutor_hint(character.note_tutor(text))
        else:
            hint += manners.standing()   # after web text his kept requests still hold (they are read, never changed from web text)
    if not initiative and DOUBT['claim']:
        hint += ' [' + recall.doubt_hint(DOUBT['claim']) + ']'
        DOUBT['claim'] = ''
    if isinstance(data, dict) and data.get('spoken') is True and not initiative and not data.get('web'):   # said aloud: the words went through speech recognition
        hint += (' [Это сказано голосом, и программа, записавшая слова, могла ослышаться. Если какое-то слово не вяжется со смыслом, '
                 'подумай, какое похожее по звучанию слово он имел в виду, и ответь по смыслу; если не уверена, коротко переспроси своими словами, '
                 'а не отвечай всерьёз на бессмыслицу.]')
        style = [p for p in str(data.get('voice') or '').split(', ') if p in hearing.STYLE_PARTS]
        if style:   # only a clear difference from his own usual voice is passed on, from the loudness and pace alone
            hint += (' [По голосу: он говорит %s. Не объявляй об этом и не делай выводов вслух, просто почувствуй, как он сейчас: '
                     'тише и медленнее может значить усталость или грусть, быстрее и громче бодрость или волнение; отвечай под это, если к месту.]'
                     % ', '.join(style))
    if not stream.ON and not (isinstance(data, dict) and data.get('web')):   # her own notes come back: when he touches one, and about once a week on their own
        if not initiative:
            rel = nook.related(text)
            if rel:
                hint += ' [В твоём уголке есть запись «%s»: %s. Если к месту, можешь сослаться на неё; не к месту, не надо.]' % rel
        again = nook.reread_hint(MEMORY.get('nook_read', 0), time.time())
        if again:
            hint += ' [' + again + ']'
            MEMORY['nook_read'] = time.time()
            save_memory()
    hint += faces.hint(data.get('fx') if isinstance(data, dict) else None, data.get('mo') if isinstance(data, dict) else None)   # the special faces her model has (the page names them)
    # Said right next to the message, where it outweighs earlier replies written in another language.
    hint += ' [Язык ответа: %s. Если он просит иной язык или перевод, сделай как просит.]' % LANGS[S.ui_lang]
    sent = user if not image and not hint else {'role': 'user', 'content': user['content'] + hint} if not image else {
        'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': image}},
                                    {'type': 'text', 'text': user['content'] + hint}]}
    scripts, carry, buffer = [], '', ''
    model_tagged = False   # the model wrote an [emotion] in this reply: then its tags are the only ones (replyfeel.py fills in only when it wrote none)
    quiet = False

    asked = []   # actions she requested this turn: the page will ask the user before anything happens
    tasks = []   # a mouse-and-keyboard job she proposes: the creator must press Start
    ue_ops = []   # Unreal operations she asks for: each needs the creator's press
    gd_ops = []   # Godot operations she asks for (work mode): each needs the creator's press
    CAPPED = {'godot': False, 'unity': False}   # set when she asked for more operations than fit in one reply
    diffs = []   # [diff:...] review of git changes in the project she was last shown (work mode): he presses Show
    sqls = []   # [sql:query]: one read-only query on a SQLite file of the project (work mode): he sees it and presses Run
    envs = []   # [env:...] read-only diagnostics of this computer (work mode): he presses Show
    scans = []   # [scan:...] audits of the project she was last shown (work mode): he presses Show
    un_ops = []   # Unity operations she asks for (work mode): each needs the creator's press
    lookups = []   # ('find' | 'search', words): searched locally after she finished speaking
    sites = []   # [go:site]: a website to open
    docreads = []   # [doc:name]: one of his documents or folders she wants to read: he presses Show
    moves = []   # [move:file >> folder]: tidying up, he presses Move
    jots = []   # [note:title >> text]: her own corner (nook.py): written at once, no plate; he is only told
    plans = []   # [plan:step | step | step]: a chain of steps he approves as a whole (the page runs them one by one, every step keeps its own plates)
    clips = []   # [clip:...]: she wants to see what he copied: he presses Show, the page reads the clipboard
    webs = []   # [web:question]: she looks it up on the internet herself (read-only)
    sums = []   # [calc:expression]: exact arithmetic done by the program, not by feel (read-only)
    tainted = isinstance(data, dict) and data.get('web') is True   # this turn follows text from the internet: nothing opens on its own
    depth = data.get('depth') if isinstance(data, dict) and isinstance(data.get('depth'), int) else 0
    reads = []   # code files she wants to see: the creator agrees first
    runs = []   # development commands she wants run in the project: the creator sees the command and presses Run
    codes = []   # code blocks of the reply: shown, not spoken
    edits = []   # ```lunaedit blocks: changes to a code file she was shown, each needs the creator's press after seeing the diff
    projs = []   # ```lunaproject blocks: a new project (set of new files) in the sandbox, needs the creator's press
    notes = []   # ```lunastandup blocks: today's stand-up she writes down after he told her
    docs = []   # ```lunadoc blocks: Word / PowerPoint / Excel she proposes, each needs the creator's press

    def sentence(piece):
        nonlocal carry, model_tagged
        if not stream.ON and not tainted:   # her corner is hers: it works on her own initiative too, but never on the stream or after web text
            for m in nook.NOTE_RE.finditer(piece):
                if len(jots) < 2:
                    jots.append(m.group(1))
        if S.agent and not initiative:   # her own initiative never gets hands: only a request from the user does
            acts = load_actions()
            for m in ACT_RE.finditer(piece):
                kind, arg = m.group(1).lower(), m.group(2).strip()
                if len(arg) > 160 and kind != 'plan':
                    continue
                if kind == 'note':
                    continue   # handled above: it is not a hand
                if kind == 'open':
                    a = acts.get(arg.lower())
                    if a and a['id'] not in [x['id'] for x in asked]:
                        asked.append(a)
                elif kind == 'doc' and S.work:
                    if not docreads:
                        docreads.append(arg)
                elif kind == 'move' and S.work:
                    if not moves:
                        moves.append(arg)
                elif kind == 'go':
                    if len(sites) < 1 and arg not in sites:
                        sites.append(arg)
                elif kind == 'web':
                    if not webs and depth < 2:
                        webs.append(arg)
                elif kind == 'calc':
                    if not sums and depth < 2:
                        sums.append(arg)
                elif kind == 'read' and S.work:
                    if len(reads) < 3 and arg not in reads:   # a few files of one project: he presses Show for each
                        reads.append(arg)
                elif kind == 'run' and S.work:
                    if len(runs) < 1:
                        runs.append(arg)
                elif kind == 'diff' and S.work:
                    if not diffs:
                        diffs.append(arg)
                elif kind == 'sql' and S.work:
                    if not sqls:
                        sqls.append(arg)
                elif kind == 'env' and S.work:
                    if not envs:
                        envs.append(arg)
                elif kind == 'scan' and S.work:
                    if not scans:
                        scans.append(arg)
                elif kind == 'unity' and S.work:
                    if len(un_ops) < 3:
                        un_ops.append(arg)
                    else:
                        CAPPED['unity'] = True   # a fourth operation is not queued: he is told, so she cannot claim it was done
                elif kind == 'gd' and S.work:
                    if len(gd_ops) < 3:
                        gd_ops.append(arg)
                    else:
                        CAPPED['godot'] = True
                elif kind == 'ue':
                    if S.unreal and len(ue_ops) < 2:
                        ue_ops.append(arg)
                elif kind == 'do':
                    if S.control and not tasks:
                        tasks.append(arg)
                elif kind == 'plan':
                    steps = parse_plan(arg)
                    if S.agent and not tainted and steps and not plans:
                        plans.append(steps)
                elif kind == 'clip':
                    if S.agent and not tainted and not clips:
                        clips.append(arg)
                elif kind in ('doc', 'move', 'read', 'run', 'gd', 'unity', 'scan', 'diff', 'env'):
                    pass   # work commands while work mode is off: nothing happens
                elif arg and (kind, arg.lower()) not in lookups:
                    lookups.append((kind, arg.lower()))
        if S.presence or stream.ON:
            piece = convo.polish(piece)
        script, spoken = clean_script(piece)
        if not spoken:   # directions only: they belong in front of the next sentence
            carry = (carry + ' ' + script).strip()
            return None
        script, carry = (carry + ' ' + script).strip(), ''
        model_tagged = model_tagged or replyfeel.has_emotion_tag(script)
        script = (replyfeel.tag_for(script, spoken, model_tagged) + ' ' + script).strip()   # no tag from the model: read it from the words
        scripts.append(script)
        return {'answer': spoken, 'script': script}

    committed = False

    def commit():
        nonlocal committed
        if committed or not (scripts or codes):
            return
        committed = True
        full = ' '.join(scripts)
        shown = (full + ''.join('\n```%s\n%s\n```' % (c['lang'], c['text'][:12000 if c['lang'] in ('lunadoc', 'lunaedit', 'lunaproject') else MAX_STORED]) for c in codes)).strip()
        if not initiative and convo.WRONG.search(str(text or '')) and len(HISTORY) >= 2 and HISTORY[-2].get('role') == 'user':   # he corrected her: remember where
            character.learn_lesson(HISTORY[-2]['content'], text)
        if S.presence and not initiative:   # he laughed at what she just said: that is now a joke of the two of them
            joke = convo.landed_joke(HISTORY, text)
            if joke:
                character.add_bits(['Он смеялся над её словами: «%s»' % joke[:120]])
        if S.presence and not initiative:   # did she claim to remember something of his that she does not know?
            DOUBT['claim'] = recall.ungrounded(full, list(MEMORY['user']) + [SUMMARY['text']] + [_m['content'] for _m in HISTORY if _m.get('role') == 'user' and isinstance(_m.get('content'), str)] + [text])
        HISTORY.extend([dict(user, content=user['content'][:MAX_STORED]), {'role': 'assistant', 'content': shown}])
        del HISTORY[:-(20 if S.presence else 12)]
        if not initiative:
            MEMORY['turns'] += 1
            character.note_activity()
            character.note_style(text)
        mood_from_script(full)
        if not initiative and data.get('web') is True and isinstance(data.get('webq'), str) and not ACT_RE.search(full):   # her own words after reading the internet
            character.learn(data['webq'], ACT_RE.sub('', full))
        save_memory()
        if not initiative and not stream.ON and MEMORY['turns'] % MEMORY_EVERY == 0:
            threading.Thread(target=update_memory, args=(list(HISTORY[-8:]),), daemon=True).start()
        if not initiative and not stream.ON and MEMORY['turns'] % REFLECT_EVERY == 0:
            threading.Thread(target=reflect, daemon=True).start()
        if S.presence and not initiative and MEMORY['turns'] - SUMMARY['turn'] >= 4:   # keep the thread of a long talk
            SUMMARY['turn'] = MEMORY['turns']
            threading.Thread(target=_app().refresh_summary, args=(list(HISTORY[-12:]),), daemon=True).start()

    try:
        if not initiative:
            character.sense(text)   # the tone of his words moves her mood and may hurt or please her
            if convo.parting(text) == 'bye':
                character.note_goodnight()   # a goodnight at night: tomorrow she can ask how he slept
            if not stream.ON:
                character.touch_opinions(text)   # her tastes grow with what you keep talking about
        thought = ''
        if S.presence and not initiative and not image and convo.worth_thinking(text):   # she thinks before she speaks
            seen_view = {}
            thought = convo.think(_app().generate, HISTORY, text, SUMMARY['text'], '; '.join('%s: %s' % (o['topic'], o['view']) for o in character.opinions_for(text)), seen_view, hard=convo.is_hard(text))
            if seen_view.get('topic') and seen_view.get('view'):
                character.set_opinion(seen_view['topic'], seen_view['view'], seen_view.get('like', 0))
        messages = [{'role': 'system', 'content': _app().system_prompt('' if initiative else text, thought)}] + HISTORY[-(20 if S.presence else 12):] + [sent]
        spoken = [False]   # has the first sentence of this reply gone out yet (it may be cut early, at a comma)
        def feed(final=False):
            """Sentences and code blocks that the buffer holds so far, in order."""
            nonlocal buffer
            segs, held = pull_code(buffer, final)
            pending = ''
            for kind, val in segs:
                if kind == 'text':
                    pending += val
                    continue
                ready, pending = split_ready(pending)
                for piece in ready + ([pending.strip()] if pending.strip() else []):
                    event = sentence(piece)
                    if event:
                        spoken[0] = True
                        yield event
                pending = ''
                codes.append(val)
                if val['lang'] == 'lunaedit':   # not shown as code: it becomes a diff plate
                    if S.agent and S.work and not initiative and len(edits) < 6:
                        edits.append(val['text'])
                    continue
                if val['lang'] == 'lunaproject':   # not shown as code: it becomes a plate listing every file
                    if S.agent and S.work and not initiative and len(projs) < 1:
                        projs.append(val['text'])
                    continue
                if val['lang'] == 'lunastandup':   # not shown as code: it is written down
                    if S.agent and S.work and not initiative and not notes:
                        notes.append(val['text'])
                    continue
                if val['lang'] == 'lunadoc':   # not shown as code: it becomes a plate
                    if S.agent and S.work and not initiative and len(docs) < 2:
                        docs.append(val['text'])
                    continue
                yield {'code': val}
            ready, pending = split_ready(pending, early=not spoken[0])
            for piece in ready + ([pending.strip()] if final and pending.strip() else []):
                event = sentence(piece)
                if event:
                    spoken[0] = True
                    yield event
            buffer = ('' if final else pending) + held

        for delta in (_app().generate_stream(messages, vision=True, max_tokens=6000) if image else _app().generate_stream(messages, max_tokens=6000)):
            buffer += delta
            quiet = quiet or '[quiet]' in buffer.lower()
            yield from feed()
        yield from feed(final=True)
        if not scripts and not codes and quiet:   # she looked at the screen and chose to say nothing
            yield {'done': True, 'quiet': True, 'mood': mood_now()}
            return
        if not scripts and not codes:
            raise RuntimeError('API вернул пустой ответ. Попробуй короткое сообщение ещё раз.')
        commit()
        if S.agent and not initiative and not tainted and not (asked or lookups or sites or webs or sums or reads or runs or docreads or moves or clips or plans):
            for kind, arg in agent.intent_commands(text, netsearch.known_site):   # he asked plainly and she forgot the command: it is still done
                (sites if kind == 'go' else lookups).append(arg if kind == 'go' else (kind, arg))
        for a in asked[:2]:
            if tainted:   # the idea may come from a web page, not from the creator: he presses Allow
                _app().PENDING[a['id']] = time.time()
                yield {'action': {'id': a['id'], 'label': a['label'], 'kind': a['kind']}}
                continue
            try:   # he asked himself: it opens at once
                _app().run_action(a)
                audit.log('open', a['label'])
                yield {'opened': a['label']}
            except OSError:
                yield {'openfail': a['label']}
        for task in tasks:
            yield {'task': control.propose(task)}
        for arg in diffs:
            plate = gitdiff.propose(arg)
            if plate:
                yield {'difffail': plate['fail']} if 'fail' in plate else {'diff': plate}
        for arg in sqls:
            plate = sqlrun.propose(arg)
            if plate:
                yield {'sqlfail': plate} if 'fail' in plate else {'sql': plate}
        for arg in envs:
            plate = envdiag.propose(arg)
            if plate:
                yield {'env': plate}
        for arg in scans:
            plate = codescan.propose(arg)
            yield {'scanfail': plate['fail']} if 'fail' in plate else {'scan': plate}
        for op in un_ops:
            plate = unity_bridge.propose(op)
            if plate:
                yield {'unityfail': plate['fail']} if 'fail' in plate else {'unity': plate}
        for op in gd_ops:
            plate = godot_bridge.propose(op)
            if plate:
                yield {'godotfail': plate['fail']} if 'fail' in plate else {'godot': plate}
        if CAPPED['godot']:
            yield {'godotfail': 'capped'}
        if CAPPED['unity']:
            yield {'unityfail': 'capped'}
        for op in ue_ops:
            plate = unreal_bridge.propose(op)
            if plate:
                yield {'unreal': plate}
        known = studio.find(text) if not initiative and _app().SING_ASK.search(text or '') else None
        if known:   # a song from her library: the recording itself is performed
            yield {'perform': {'id': known['id'], 'title': known['title'], 'bpm': known.get('bpm', 0), 'her': bool(known.get('her'))}}
        for cmd in runs:
            plate = runner.propose(cmd)
            yield {'runfail': plate['fail']} if 'fail' in plate else {'run': plate}
        for src in notes:
            if standup.save(src):
                yield {'standup': True}
        for src in docs:
            plate = office.propose(src)
            yield {'document': plate} if plate else {'docfail': True}
        for src in edits:
            try:
                yield {'edit': codeedit.propose(src)}
            except ValueError as exc:
                yield {'editfail': str(exc)}
        for src in projs:
            try:
                yield {'project': projects.propose(src)}
            except ValueError as exc:
                yield {'projectfail': str(exc)}
        for name in reads:
            items = devtools.find_code(name)
            yield {'readfile': {'query': name, 'items': items}} if items else {'notfound': name}
        for arg in jots:
            parsed = nook.parse(arg)
            if not parsed:
                continue
            try:
                done = nook.write(*parsed)
                audit.log('nook', done['file'], True)
                yield {'noted': {'title': done['title'], 'added': done['added']}}
            except (ValueError, OSError) as exc:
                yield {'notefail': str(exc)}
        for steps in plans:
            yield {'plan': {'steps': steps}}   # nothing runs before he presses Start on the page
        for _ in clips:
            yield {'clip': True}   # the page asks him; nothing is read before he presses Show
        for name in docreads:
            items = docfiles.find(name)
            yield {'docfile': {'query': name, 'items': items}} if items else {'notfound': name}
        for spec in moves:
            plate = docfiles.propose_move(spec)
            yield {'movefail': plate['fail']} if 'fail' in plate else {'move': plate}
        for site in sites:
            found = netsearch.resolve_site(site)
            if found:   # a listed name or a public address: opens at once, as before
                item = agent.offer('url', found[0], found[1])
                yield from open_item(item, tainted, {'query': site, 'items': [item]})
                continue
            # an unknown name: look it up and let him confirm; nothing opens until he presses
            items = [agent.offer('url', url, title, urllib.parse.urlsplit(url).hostname or '')
                     for url, title in netsearch.site_candidates(site)]
            yield {'choices': {'query': site, 'items': items}} if items else {'notfound': site}
        for kind, words in lookups[:2]:
            if kind == 'search':
                item = agent.google(words)
                yield from open_item(item, tainted, {'query': words, 'search': True, 'items': [item]})
            else:
                items = agent.find(words)
                if len(items) == 1:
                    yield from open_item(items[0], tainted, {'query': words, 'items': items})
                else:
                    yield {'choices': {'query': words, 'items': items}} if items else {'notfound': words}
        for question in webs:   # read-only research: the page sends the excerpts back to her as data
            found = netsearch.research(question)
            if found:
                yield {'web': {'query': question, 'text': security.neutralize(ACT_RE.sub('', found), 6000), 'depth': depth + 1}}
            else:
                yield {'webfail': question}
        for expr in sums:
            result = exact.calc(expr)
            yield {'calc': {'query': expr, 'text': result, 'depth': depth + 1}} if result else {'calcfail': expr}
        yield {'done': True, 'mood': mood_now()}
    finally:
        commit()   # also when the page interrupted her: remember what was actually said


def open_item(item, tainted, plate):
    """Something she found for him (a site, a Google tab, one file): opened at once when he asked, else shown for his press."""
    if tainted:
        yield {'choices': plate}
        return
    entry = agent.take(item['token'])
    try:
        agent.launch(entry)
        audit.log('open', entry['label'])
        yield {'opened': entry['label']}
    except (OSError, AttributeError, TypeError):
        yield {'openfail': item['label']}


def end_task():
    """Finish a mouse-and-keyboard task and write it to the journal (once, only if one was running)."""
    if control.SESSION.get('on'):
        audit.log('task.end', control.SESSION.get('acts', 0))
    control.end()
