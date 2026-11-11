"""Her hands, part 3: work the mouse and keyboard on a task (stage 2).
A task starts only after the creator pressed Start on a plate that names it. Then the page repeats:
screenshot -> plan_step (the vision model proposes ONE action) -> confirmation if the action is risky -> run_action.
The server enforces the limits itself, whatever the page says: a step and time budget, a fixed action vocabulary,
a short key list (see inputctl.py), and a stop as soon as the creator touches the mouse."""
import json
import re
import secrets
import time

import inputctl

TTL = 120
TASKS = {}                       # token -> (task text, time): proposed by her, waiting for the creator's Start
SESSION = {'on': False, 'until': 0.0, 'steps': 0, 'acts': 0, 'pos': None, 'task': ''}
MAX_STEPS, MAX_ACTS, MAX_SECONDS_TASK, MOVED_PX = 30, 40, 360, 40
ACTIONS = {'click', 'double_click', 'right_click', 'type', 'key', 'scroll', 'wait', 'done', 'fail'}

STEP_PROMPT = (
    'You operate a Windows computer for your creator by looking at a screenshot and choosing exactly ONE next action. '
    'Answer with a single JSON object and nothing else: {"thought": "what you see and what you do now, one short sentence in %(lang)s", '
    '"action": "click|double_click|right_click|type|key|scroll|wait|done|fail", "x": 0-1000, "y": 0-1000, "text": "...", '
    '"key": "ctrl+a", "amount": -10..10, "say": "one friendly sentence in %(lang)s", "risky": false}. '
    'x and y are relative to the screenshot: 0,0 is the top-left corner, 1000,1000 the bottom-right; aim at the centre of the '
    'target. click/double_click/right_click use x,y. type puts text into the focused field (click the field first). key presses '
    'one combination: enter, tab, esc, backspace, delete, arrows, home, end, pageup, pagedown, ctrl+a/c/v/x/z/y/s/f/n/o/t/w/p. '
    'scroll uses x,y and amount (positive up, negative down). wait pauses 1.5 s while something loads. '
    'done = the task is finished (say what you did). fail = you cannot continue (say why).\n'
    'Rules: do only what the task says. Never type passwords, card numbers or personal data; if a login, captcha, payment or '
    'anything unexpected appears, answer fail. Set "risky": true for any action that sends, posts, submits, pays, deletes or '
    'overwrites something, or closes unsaved work. One action per answer. If the same action did not help twice, answer fail. '
    'The screenshot is the truth: do not assume a step worked until you see it.')


def propose(text):
    """She asked to do a task: remember it for two minutes, the creator decides."""
    now = time.time()
    for k in [k for k, v in TASKS.items() if now - v[1] > TTL]:
        del TASKS[k]
    token = secrets.token_hex(8)
    TASKS[token] = (text.strip()[:160], now)
    return {'token': token, 'text': TASKS[token][0]}


def begin(token):
    entry = TASKS.pop(token, None) if isinstance(token, str) else None
    if not entry or time.time() - entry[1] > TTL:
        return False
    SESSION.update(on=True, until=time.time() + MAX_SECONDS_TASK, steps=0, acts=0, pos=None, task=entry[0])
    return True


def end():
    SESSION.update(on=False, pos=None)


def live():
    if SESSION['on'] and time.time() > SESSION['until']:
        end()
    return SESSION['on']


def clean_action(a):
    """An action from the model or the page -> a strictly validated copy; ValueError if it is anything else."""
    if not isinstance(a, dict) or a.get('action') not in ACTIONS:
        raise ValueError('action')
    kind, out = a['action'], {'action': a['action']}
    if kind in ('click', 'double_click', 'right_click', 'scroll'):
        for k in ('x', 'y'):
            v = a.get(k)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1000:
                raise ValueError(k)
            out[k] = float(v)
    if kind == 'scroll':
        v = a.get('amount')
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError('amount')
        out['amount'] = max(-10, min(10, int(v)))
    if kind == 'type':
        t = a.get('text')
        if not isinstance(t, str) or not 1 <= len(t) <= 300:
            raise ValueError('text')
        out['text'] = t
    if kind == 'key':
        parts = inputctl.parse_combo(a.get('key'))
        if parts is None:
            raise ValueError('key')
        out['key'] = '+'.join(parts)
    out['risky'] = bool(a.get('risky')) or out.get('key') in ('delete', 'ctrl+x')
    return out


def plan_step(image, steps, lang, ask):
    """Show the screenshot to the vision model: {action, thought, say}. `ask(messages)` returns the reply text."""
    if not live() or SESSION['steps'] >= MAX_STEPS:
        end()
        raise PermissionError('budget')
    SESSION['steps'] += 1
    done = '\n'.join('%d. %s' % (i + 1, s[:120]) for i, s in enumerate(steps[-12:])) or '(nothing yet)'
    question = 'Task: %s\nSteps already done:\n%s\nWhat is the next action?' % (SESSION['task'], done)
    messages = [{'role': 'system', 'content': STEP_PROMPT % {'lang': lang}},
                {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': image}},
                                             {'type': 'text', 'text': question}]}]
    raw = ask(messages)
    m = re.search(r'\{.*\}', raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
        action = clean_action(data)
    except (ValueError, TypeError):
        raise RuntimeError('Не удалось понять ответ модели, остановилась.') from None
    return {'action': action, 'thought': str(data.get('thought') or '')[:200], 'say': str(data.get('say') or '')[:240]}


def run_action(a):
    """Do one action the creator allowed. PermissionError('moved') when a hand took the mouse, ('budget') when spent."""
    action = clean_action(a)
    if not live() or SESSION['acts'] >= MAX_ACTS:
        end()
        raise PermissionError('budget')
    pos, now = SESSION['pos'], inputctl.cursor()
    if pos and max(abs(now[0] - pos[0]), abs(now[1] - pos[1])) > MOVED_PX:
        end()
        raise PermissionError('moved')   # a hand on the mouse always wins
    SESSION['acts'] += 1
    kind = action['action']
    if kind in ('click', 'double_click', 'right_click'):
        inputctl.click(action['x'], action['y'], 'right' if kind == 'right_click' else 'left', 2 if kind == 'double_click' else 1)
    elif kind == 'scroll':
        inputctl.scroll(action['x'], action['y'], action['amount'])
    elif kind == 'type':
        inputctl.type_text(action['text'])
    elif kind == 'key':
        inputctl.press(action['key'])
    elif kind == 'wait':
        time.sleep(1.5)
    SESSION['pos'] = inputctl.cursor()
