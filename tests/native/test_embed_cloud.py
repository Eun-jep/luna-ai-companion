"""Meaning through the cloud service she already thinks with: opt-in only, one batched request, the key never in the way out, and a dead network costs one timeout."""
import pytest

from luna.core import character, feeling, memory_store, providers


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    saved = (dict(providers._choice), dict(providers._keys))
    monkeypatch.setattr(providers, '_save_choice', lambda: None)
    providers._keys['gemini'] = 'k' * 20
    providers._choice.update(active='gemini', embed=False)
    yield
    memory_store.set_embedder(None, None)
    feeling.reset()
    providers._choice.clear(); providers._choice.update(saved[0])
    providers._keys.clear(); providers._keys.update(saved[1])


def fake_service(calls):
    def call(url, key=None, body=None, timeout=15):
        calls.append((url, key, body))
        return {'data': [{'index': i, 'embedding': [1.0 + i] * 1000} for i, _ in enumerate(body['input'])][::-1]}   # out of order on purpose
    return call


def test_off_by_default_and_needs_a_service_that_can_embed():
    assert providers.embed_spec() == ''
    providers.set_embed(True)
    assert providers.embed_spec() == 'cloud:gemini'
    providers._choice['active'] = 'zai'
    providers._keys['zai'] = 'z' * 20
    assert providers.embed_possible() is False and providers.embed_spec() == ''
    providers._choice['active'] = ''
    assert providers.embed_spec() == ''


def test_state_tells_the_page(monkeypatch):
    monkeypatch.setattr(providers, 'scan_local', lambda: [])
    got = providers.state()['embed']
    assert got == {'on': False, 'can': True, 'name': 'Google Gemini'}


def test_one_request_for_many_texts_in_order_and_cut(monkeypatch):
    calls = []
    monkeypatch.setattr(providers, '_call', fake_service(calls))
    name, one, many = providers.embedder('gemini')
    assert name == 'cloud:gemini:gemini-embedding-001'
    vecs = many(['a', 'b', 'c'])
    assert len(calls) == 1 and calls[0][0].endswith('/openai/embeddings') and calls[0][1] == 'k' * 20
    assert calls[0][2] == {'model': 'gemini-embedding-001', 'input': ['a', 'b', 'c']}
    assert [v[0] for v in vecs] == [1.0, 2.0, 3.0] and all(len(v) == 768 for v in vecs)   # back in order, cut to the working size
    assert len(one('x')) == 768


def test_prefetch_fills_the_cache_so_recall_needs_one_request(monkeypatch):
    calls = []
    monkeypatch.setattr(providers, '_call', fake_service(calls))
    memory_store.set_embedder(*providers.embedder('gemini'))
    memory_store.similarities('query', ['fact %d' % i for i in range(10)])
    assert len(calls) == 1 and len(calls[0][2]['input']) == 11
    memory_store.similarities('query', ['fact %d' % i for i in range(10)])
    assert len(calls) == 1   # everything is cached now


def test_a_dead_network_costs_one_try_not_one_per_fact(monkeypatch):
    calls = []

    def dead(*a, **k):
        calls.append(1)
        raise providers.ProviderError('network')
    monkeypatch.setattr(providers, '_call', dead)
    memory_store.set_embedder(*providers.embedder('gemini'))
    got = memory_store.similarities('собаку', ['у него живёт собака Мишка'] + ['факт %d' % i for i in range(30)])
    assert len(calls) == 1 and got[0] > 0   # the word-form match took over
    memory_store.vector('another')
    assert len(calls) == 1   # still resting


def test_use_embeddings_follows_the_choice(monkeypatch):
    monkeypatch.setattr(feeling, 'warm', lambda name: None)   # no background warm-up (it would call the real service with a made-up key)
    providers.set_embed(True)
    assert character.use_embeddings('cloud:gemini') is True
    assert memory_store._embedder[0].startswith('cloud:gemini')
    assert character.use_embeddings('cloud:openai') is False   # not the active service: nothing goes anywhere
    assert memory_store._embedder is None
    providers._choice['active'] = 'zai'
    assert character.use_embeddings('cloud:zai') is False


def test_unknown_service_is_refused():
    with pytest.raises(providers.ProviderError):
        providers.embedder('zai')
