"""A small hand-made catalog that explains the models in the picker: how fast or smart each is, whether it is free, whether it sees pictures.
It is guidance, not truth: matched by name patterns, so an unknown model simply gets no label. Pure data and matching, no network, nothing downloaded.

describe(provider id, model id) -> {'tier': 'fast'|'balanced'|'smart'|'', 'vision': bool, 'free': bool, 'rec': bool}
suggestions() -> local models worth installing (the page shows the command; nothing is run for the user)."""
import re

from luna.core import providers

# (provider or None for any, name pattern, tier, vision, free); the first matching rule wins
RULES = [
    ('zai', r'glm-4\.\dv', 'fast', True, True),
    ('zai', r'glm-4\.5-flash', 'fast', False, True),
    ('zai', r'glm-4\.5-air', 'balanced', False, False),
    ('zai', r'glm-4\.[67]', 'smart', False, False),
    ('openai', r'gpt-4o-mini|gpt-4\.1-(mini|nano)|gpt-5-(mini|nano)', 'fast', True, False),
    ('openai', r'^o\d|gpt-5(?!-(mini|nano))', 'smart', False, False),
    ('openai', r'gpt-4o|gpt-4\.1|gpt-4-turbo', 'balanced', True, False),
    ('anthropic', r'haiku', 'fast', True, False),
    ('anthropic', r'sonnet', 'balanced', True, False),
    ('anthropic', r'opus', 'smart', True, False),
    ('gemini', r'flash-lite|flash', 'fast', True, False),
    ('gemini', r'pro', 'smart', True, False),
    ('openrouter', r':free$', 'balanced', False, True),
]
# local models are told apart by their size in the name (llama3.2:3b, qwen2.5:14b, ...)
SIZE_RE = re.compile(r'(?<![\d.])(\d+(?:\.\d+)?)\s*b(?![a-z])', re.I)

SUGGEST = [   # sizes are approximate downloads
    {'model': 'llama3.2:3b', 'gb': 2.0, 'ram': 4, 'vision': False, 'tier': 'fast'},
    {'model': 'qwen2.5:7b', 'gb': 4.7, 'ram': 8, 'vision': False, 'tier': 'balanced'},
    {'model': 'gemma3:4b', 'gb': 3.3, 'ram': 8, 'vision': True, 'tier': 'balanced'},
    {'model': 'qwen2.5:14b', 'gb': 9.0, 'ram': 16, 'vision': False, 'tier': 'smart'},
]


def _local_tier(model):
    m = SIZE_RE.search(model)
    if not m:
        return ''
    size = float(m.group(1))
    return 'fast' if size < 5 else 'balanced' if size < 12 else 'smart'


def describe(pid, model):
    out = {'tier': '', 'vision': bool(providers.VISION_HINT.search(model)), 'free': False, 'rec': False}
    if pid in providers.CLOUD:
        out['rec'] = model == providers.CLOUD[pid]['default']
        out['free'] = model in providers.CLOUD[pid].get('free', [])
        for owner, pattern, tier, vision, free in RULES:
            if owner in (None, pid) and re.search(pattern, model, re.I):
                out.update(tier=tier, vision=out['vision'] or vision, free=out['free'] or free)
                break
    else:
        out['tier'] = _local_tier(model)
        out['free'] = True   # runs on this computer
    return out


def describe_all(pid, models):
    return {m: describe(pid, m) for m in models}


def suggestions(installed=()):
    """Local models to suggest for Ollama, without those that are already installed."""
    return [dict(s, command='ollama pull ' + s['model']) for s in SUGGEST if not any(m.startswith(s['model']) for m in installed)]
