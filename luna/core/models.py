"""The Live2D models on disk: which are complete, their expression and motion files, the display names of their parameters. Read-only."""
import json
from urllib.parse import quote

from luna import paths

ROOT = paths.ROOT
MODELS = ROOT / 'assets' / 'models'


def url_for(path):
    return '/' + '/'.join(quote(part) for part in path.relative_to(ROOT).parts)


def missing_files(model_file):
    """Files named in a model3.json that are absent on disk (e.g. archive extracted with the
    wrong filename encoding). Returns [] when the model is complete."""
    try:
        refs = json.loads(model_file.read_text(encoding='utf-8-sig')).get('FileReferences', {})
    except (OSError, ValueError):
        return ['model3.json']
    names = [refs.get('Moc'), refs.get('Physics')] + list(refs.get('Textures', []))
    return [n for n in names if n and not (model_file.parent / n).is_file()]


def list_models():
    """Every complete Live2D model under assets/models, with its loose expression files."""
    models = []
    for model_file in sorted(MODELS.rglob('*.model3.json')):
        folder = model_file.parent
        if missing_files(model_file):
            continue
        top = model_file.relative_to(MODELS).parts[0]
        expressions = [{'name': f.name[:-len('.exp3.json')], 'url': url_for(f)}
                       for f in sorted(folder.rglob('*.exp3.json'))]
        models.append({'id': top, 'name': '%s · %s' % (top, folder.name),
                       'url': url_for(model_file), 'expressions': expressions, 'labels': parameter_labels(folder),
                       'motions': [{'name': f.name[:-len('.motion3.json')], 'url': url_for(f)} for f in sorted(folder.rglob('*.motion3.json'))[:30]]})
    return models


def parameter_labels(folder):
    """{parameter id: its display name} from the model's .cdi3.json: for expression files named 1, 2, 3 or Button7 this is what tells what the face is (blush, tears)."""
    labels = {}
    for path in sorted(folder.rglob('*.cdi3.json'))[:1]:
        try:
            for p in json.loads(path.read_text(encoding='utf-8-sig')).get('Parameters', []):
                if isinstance(p, dict) and isinstance(p.get('Id'), str) and isinstance(p.get('Name'), str):
                    labels[p['Id']] = p['Name'][:40]
        except (OSError, ValueError):
            pass
    return labels
