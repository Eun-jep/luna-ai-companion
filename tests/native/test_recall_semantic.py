"""character.recall uses the meaning of a fact when an embedding model is set, and still works when there is none (or it is down)."""
import pytest

import character
import memory_store


@pytest.fixture(autouse=True)
def clean():
    saved = {k: list(character.MEMORY[k]) for k in ('user', 'me')}
    yield
    memory_store.set_embedder(None, None)
    for k, v in saved.items():
        character.MEMORY[k] = v


def fake_embedder(text):
    t = text.lower()
    # two "topics": pets and cooking; no shared words between a query and its fact
    return [1.0 if any(w in t for w in ('питом', 'кошк', 'пёс')) else 0.0, 1.0 if any(w in t for w in ('суп', 'борщ', 'готовить')) else 0.0, 0.05]


def facts():
    return ['любит гулять по ночам'] * 1 + ['у него есть кошка по имени Муся'] + ['работает в банке %d' % i for i in range(14)]


def test_meaning_pulls_the_right_fact(monkeypatch):
    character.MEMORY['user'] = facts()
    memory_store.set_embedder('fake', fake_embedder)
    got = character.recall('user', 'расскажи про моего питомца', k=3)
    assert 'у него есть кошка по имени Муся' in got


def test_without_a_model_it_still_returns_k_items():
    character.MEMORY['user'] = facts()
    got = character.recall('user', 'расскажи про моего питомца', k=3)
    assert len(got) == 3


def test_down_model_never_breaks_recall():
    def broken(text):
        raise OSError('down')
    character.MEMORY['user'] = facts()
    memory_store.set_embedder('broken', broken)
    assert len(character.recall('user', 'что-нибудь', k=3)) == 3


def test_use_embeddings_switch():
    assert character.use_embeddings('ollama:nomic-embed-text') is True
    assert character.use_embeddings(None) is False
    assert character.use_embeddings('http://evil') is False
