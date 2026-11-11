"""memory_store.py: word-form matching, optional embedding model with SQLite cache, and that recall never breaks."""
import pytest

import memory_store as ms

FACTS = ['У него живёт собака по имени Мишка', 'Он любит кофе по утрам', 'Работает программистом в Сеуле', 'Мечтает поехать в Японию летом']


@pytest.fixture(autouse=True)
def clean():
    ms.set_embedder(None, None)
    ms.configure_cache(None)
    yield
    ms.set_embedder(None, None)
    ms.configure_cache(None)


def best(query):
    scores = ms.similarities(query, FACTS)
    return max(range(len(FACTS)), key=lambda i: scores[i]), max(scores)


def test_other_word_forms_find_the_fact():
    assert best('расскажи про свою собаку')[0] == 0
    assert best('собаку надо выгулять')[0] == 0
    assert best('хочу в японию на лето')[0] == 3
    assert best('работа программиста')[0] == 2


def test_name_is_found():
    assert best('мишка соскучился')[0] == 0


def test_unrelated_text_scores_zero():
    assert best('погода сегодня холодная')[1] == 0.0


def test_stopwords_alone_do_not_match():
    assert best('это что как')[1] == 0.0


def test_empty_inputs():
    assert ms.similarities('', FACTS) == [0.0] * 4
    assert ms.similarities('собака', []) == []


def test_word_similarity_rules():
    assert ms.word_similarity('собака', 'собака') == 1.0
    assert ms.word_similarity('собаку', 'собака') == 0.9
    assert ms.word_similarity('кот', 'собака') == 0.0
    assert ms.word_similarity('кофе', 'кофейня') == 0.9      # a long shared start


def test_cjk_pairs():
    assert ms.similarities('旅行に行きたい', ['去年は旅行をした', '猫が好き'])[0] > 0


def fake_embedder(calls):
    topics = {'dog': ('собак', 'пес', 'пёс', 'питом'), 'coffee': ('кофе', 'чай', 'напит')}

    def embed(text):
        calls.append(text)
        low = text.lower()
        return [1.0 if any(w in low for w in topics['dog']) else 0.0, 1.0 if any(w in low for w in topics['coffee']) else 0.0, 0.2]
    return embed


def test_embedder_finds_synonyms_and_is_cached(tmp_path):
    calls = []
    ms.configure_cache(tmp_path / 'vec.db')
    ms.set_embedder('fake', fake_embedder(calls))
    scores = ms.similarities('мой питомец заболел', FACTS)
    assert scores[0] > 0.5 and scores[1] == 0.0   # "питомец" ~ "собака" only through the model
    first = len(calls)
    ms.similarities('мой питомец заболел', FACTS)
    assert len(calls) == first                    # all vectors came from the cache
    ms.set_embedder('fake', fake_embedder(calls))  # memory cache cleared: now SQLite serves them
    ms.similarities('мой питомец заболел', FACTS)
    assert len(calls) == first


def test_broken_embedder_falls_back_to_word_forms():
    def boom(text):
        raise OSError('model is down')
    ms.set_embedder('broken', boom)
    scores = ms.similarities('собаку надо выгулять', FACTS)
    assert scores[0] > 0.3


def test_nan_embedding_is_rejected():
    ms.set_embedder('nan', lambda text: [float('nan'), 1.0])
    assert ms.similarities('собаку надо выгулять', FACTS)[0] > 0.3   # fell back


def test_ollama_embedder_accepts_only_loopback():
    ms.ollama_embedder('http://127.0.0.1:11434')
    ms.ollama_embedder('http://localhost:11434')
    for bad in ('http://evil.example:11434', 'https://127.0.0.1:11434', 'http://127.0.0.1.evil.example'):
        with pytest.raises(ValueError):
            ms.ollama_embedder(bad)
