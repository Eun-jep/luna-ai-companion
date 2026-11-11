"""The model catalog (luna/core/catalog.py): labels for the picker, suggestions for local models."""
import pytest

from luna.core import catalog, providers


@pytest.mark.parametrize('pid, model, tier, vision, free', [
    ('zai', 'glm-4.5-flash', 'fast', False, True),
    ('zai', 'glm-4.6v-flash', 'fast', True, True),
    ('zai', 'glm-4.6', 'smart', False, False),
    ('openai', 'gpt-4o-mini', 'fast', True, False),
    ('openai', 'gpt-4o', 'balanced', True, False),
    ('openai', 'o3', 'smart', False, False),
    ('anthropic', 'claude-haiku-5-5', 'fast', True, False),
    ('anthropic', 'claude-opus-5-5', 'smart', True, False),
    ('gemini', 'gemini-2.0-flash', 'fast', True, False),
    ('openrouter', 'meta-llama/llama-3.3-70b-instruct:free', 'balanced', False, True),
    ('ollama', 'llama3.2:3b', 'fast', False, True),
    ('ollama', 'qwen2.5:7b', 'balanced', False, True),
    ('ollama', 'qwen2.5:14b', 'smart', False, True),
    ('ollama', 'llava:7b', 'balanced', True, True),
])
def test_known_models_are_described(pid, model, tier, vision, free):
    d = catalog.describe(pid, model)
    assert (d['tier'], d['vision'], d['free']) == (tier, vision, free)


def test_unknown_model_gets_no_label_and_no_error():
    d = catalog.describe('openai', 'something-new')
    assert d == {'tier': '', 'vision': False, 'free': False, 'rec': False}
    assert catalog.describe('ollama', 'mystery')['tier'] == ''


def test_default_model_is_recommended():
    for pid, spec in providers.CLOUD.items():
        assert catalog.describe(pid, spec['default'])['rec']


def test_every_listed_cloud_model_has_a_tier():
    for pid, spec in providers.CLOUD.items():
        for m in spec['models']:
            assert catalog.describe(pid, m)['tier'], (pid, m)


def test_suggestions_skip_installed_and_only_give_commands():
    s = catalog.suggestions(['qwen2.5:7b-instruct-q4_K_M'])
    assert 'qwen2.5:7b' not in [x['model'] for x in s]
    assert all(x['command'] == 'ollama pull ' + x['model'] for x in s) and len(s) == len(catalog.SUGGEST) - 1


def test_suggested_names_are_plain_model_names():
    import re
    assert all(re.fullmatch(r'[a-z0-9.]+:[0-9.]+b', x['model']) for x in catalog.SUGGEST)
