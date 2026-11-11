"""Shows how the meaning-based tone (luna/core/feeling.py) reads your own phrases, to tune MIN_SIM and MARGIN for the embedding model you use.
Needs Ollama running with the model (ollama pull nomic-embed-text). Usage:  python tools/feeling_check.py "phrase one" "phrase two" ...
Nothing leaves the computer; without arguments a few sample phrases are used."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from luna.core import feeling, memory_store  # noqa: E402

SAMPLES = ['честно, сегодня всё какое-то серое', 'I finally did it, they said yes!', 'ugh, my head is splitting and I am freezing',
           'open the calendar for tomorrow', 'опять всё сломалось, как же я зол', 'thanks, that really saved my evening']


def main():
    model = 'nomic-embed-text'
    memory_store.set_embedder(*memory_store.ollama_embedder(model=model))
    feeling.warm('ollama:' + model)
    import time
    for _ in range(600):
        if ('ollama:' + model) in feeling._pool:
            break
        if feeling._failed[0]:
            sys.exit('the embedding model does not answer: is Ollama running and the model pulled?')
        time.sleep(0.1)
    for text in sys.argv[1:] or SAMPLES:
        got = feeling.scores(text)
        if got is None:
            print('?', text)
            continue
        best = max((t for t in got if t), key=got.get)
        print('%-8s %s' % (feeling.classify(text) or '-', text))
        print('         ' + '  '.join('%s=%.2f' % (t or 'everyday', v) for t, v in sorted(got.items(), key=lambda kv: -kv[1])), '(best: %s)' % best)


if __name__ == '__main__':
    main()
