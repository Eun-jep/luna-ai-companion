"""The first piece of a reply may be cut at a comma (the voice starts sooner); everything else is still cut at sentence ends."""
from luna.core.script import split_ready

LONG = 'Знаешь, я сегодня целый день думала о нашем вчерашнем разговоре, и вот что поняла'


def test_default_waits_for_sentence_end():
    assert split_ready(LONG) == ([], LONG)


def test_early_cuts_first_clause_when_long_enough():
    ready, rest = split_ready(LONG, early=True)
    assert ready and ready[0].endswith(',') and len(ready[0]) >= 28
    assert (ready[0] + ' ' + rest.strip()).replace('  ', ' ') == LONG or ready[0] + rest == LONG


def test_early_does_not_cut_short_clause():
    assert split_ready('Да, конечно, я помню этот день и всё остальное', early=True)[0] == []
    assert split_ready('Да, ну', early=True)[0] == []


def test_early_never_cuts_inside_a_command():
    text = 'Сейчас открою это для тебя [open:мои документы, и ещё'
    ready, _ = split_ready(text, early=True)
    assert all('[open' not in p for p in ready)


def test_sentence_end_still_wins():
    ready, rest = split_ready('Это первая фраза, она длинная и законченная. А это вторая', early=True)
    assert ready == ['Это первая фраза, она длинная и законченная.'] and rest.strip() == 'А это вторая'
