"""settings.json: the character (name, personality, default model). Read once; the dict is shared by everything that imports it."""
import json

from luna import paths

CONFIG = json.loads((paths.ROOT / 'settings.json').read_text(encoding='utf-8'))
