"""Which optional libraries are missing, and what stops working without them.
The server itself needs only the standard library; each of these adds a feature. A missing one must never crash the app:
it is reported in plain words (with the exact command) and the feature stays off."""
import importlib.util

# module -> (pip name, what it is for)
LIBS = {
    'numpy': ('numpy', 'hearing and song recognition'),
    'sounddevice': ('sounddevice', 'microphone'),
    'soundcard': ('soundcard', 'listening to the computer\'s sound'),
    'vosk': ('vosk', 'speech recognition'),
    'sherpa_onnx': ('sherpa-onnx', 'Russian/Korean/Japanese speech recognition'),
    'edge_tts': ('edge-tts', 'cloud voice'),
    'docx': ('python-docx', 'Word documents'),
    'pptx': ('python-pptx', 'PowerPoint presentations'),
    'openpyxl': ('openpyxl', 'Excel tables'),
    'pypdf': ('pypdf', 'reading PDF'),
}


def missing(find=importlib.util.find_spec):
    """-> [(module, pip name, purpose)] for the libraries that are not installed."""
    return [(m, pip, why) for m, (pip, why) in LIBS.items() if find(m) is None]


def report(find=importlib.util.find_spec):
    """A short text for the console / log, or '' when everything is installed."""
    gone = missing(find)
    if not gone:
        return ''
    lines = ['Not installed (these features are off): ' + ', '.join('%s (%s)' % (pip, why) for _, pip, why in gone),
             'Install everything with:  py -m pip install -r requirements.txt']
    return '\n'.join(lines)
