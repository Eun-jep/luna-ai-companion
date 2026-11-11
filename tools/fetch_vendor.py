"""Download the third-party browser libraries into web/vendor/ so that the page works without internet (offline).

    py tools/fetch_vendor.py            download what is missing, check every file against its pinned SHA-256
    py tools/fetch_vendor.py --check    only check, download nothing (exit code 1 when something is missing or wrong)
    py tools/fetch_vendor.py --pin      print the SHA-256 of the files in web/vendor/ (to update PINS after raising a version)

The files are NOT kept in git (see .gitignore): the Live2D Cubism Core is proprietary software under the Live2D licence and must come from
Live2D itself. The page tries web/vendor/ first and falls back to the CDN when a file is absent, so nothing breaks if this was never run.
Pure standard library."""
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / 'web' / 'vendor'
MP = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14'

# local name -> (source URL, SHA-256 or '' while not pinned yet)
FILES = {
    'pixi.min.js': ('https://cdnjs.cloudflare.com/ajax/libs/pixi.js/6.5.10/browser/pixi.min.js', ''),
    'unsafe-eval.min.js': ('https://cdn.jsdelivr.net/npm/@pixi/unsafe-eval@6.5.10/dist/browser/unsafe-eval.min.js', ''),   # lets Pixi 6 run without eval (the page's CSP has no 'unsafe-eval')
    'live2dcubismcore.min.js': ('https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js', ''),
    'cubism4.min.js': ('https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/dist/cubism4.min.js', ''),
    'mediapipe/vision_bundle.mjs': (MP + '/vision_bundle.mjs', ''),
    'mediapipe/wasm/vision_wasm_internal.js': (MP + '/wasm/vision_wasm_internal.js', ''),
    'mediapipe/wasm/vision_wasm_internal.wasm': (MP + '/wasm/vision_wasm_internal.wasm', ''),
    'mediapipe/wasm/vision_wasm_nosimd_internal.js': (MP + '/wasm/vision_wasm_nosimd_internal.js', ''),
    'mediapipe/wasm/vision_wasm_nosimd_internal.wasm': (MP + '/wasm/vision_wasm_nosimd_internal.wasm', ''),
    'mediapipe/face_landmarker.task': ('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task', ''),
}
# local name -> SHA-256 of the file as downloaded on 2026-11-11. live2dcubismcore.min.js is a "latest" file at Live2D: if Live2D publishes a new
# Core the check says "wrong"; look at the new file, then run --pin and update this table on purpose.
PINS = {
    'pixi.min.js': '403f2f2ee8145fa17f60c5c89403056efe2680e5096ec2762036486914ed19c5',
    'unsafe-eval.min.js': '94bb4bfdbd015087772ee03bc4117e253c326e8ca73a61646bd331b22f6847ad',
    'live2dcubismcore.min.js': '25ae938cb4fe282ce189b357bcc97e603d1e1f7ec78bf04150d401c23cdc792f',
    'cubism4.min.js': 'af1267e6d52759b245766c578d905bfa025b532d5c3cc727c370957c4409e21b',
    'mediapipe/vision_bundle.mjs': 'e77f281f9619150d937023c355bae170e9120e3b9e43f1e23a2a7bee07197669',
    'mediapipe/wasm/vision_wasm_internal.js': '9440cf0cc0cea21800e31581ec32aeedcc5fbf9df4509796bbc7d3f99e52ab9c',
    'mediapipe/wasm/vision_wasm_internal.wasm': 'f82a8e6c05e08a44cc9f9e7ec5f845935bcbb1b1500ebe8c2f4812fb4e2917dc',
    'mediapipe/wasm/vision_wasm_nosimd_internal.js': 'abe9b6fbeaf86fcb53a5edce3926c82ccb0619e18fed4d9d9ce561ee7f55e054',
    'mediapipe/wasm/vision_wasm_nosimd_internal.wasm': '38b61feab2fd7934e05cbe9f68baa308978a5e3b7f85c1913bb8ae89b8ef8b97',
    'mediapipe/face_landmarker.task': '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff',
}
MAX_BYTES = 40 << 20


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def fetch(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': 'luna-fetch-vendor'})
    with urllib.request.urlopen(request, timeout=60) as response, open(tmp, 'wb') as out:   # noqa: S310 - fixed https URLs above
        total = 0
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            total += len(block)
            if total > MAX_BYTES:
                raise ValueError('too big')
            out.write(block)
    tmp.replace(target)


def status():
    """-> [(name, state)] with state in ok / missing / wrong."""
    out = []
    for name in FILES:
        path = VENDOR / name
        if not path.is_file():
            out.append((name, 'missing'))
        elif PINS.get(name) and sha256(path) != PINS[name]:
            out.append((name, 'wrong'))
        else:
            out.append((name, 'ok'))
    return out


def main(argv):
    if '--pin' in argv:
        for name in FILES:
            if (VENDOR / name).is_file():
                print("    %r: %r," % (name, sha256(VENDOR / name)))
        return 0
    if '--check' not in argv:
        for name, state in status():
            if state == 'ok':
                continue
            url = FILES[name][0]
            print('downloading', name)
            try:
                fetch(url, VENDOR / name)
            except (OSError, ValueError) as exc:
                print('  failed:', exc)
    bad = [(n, s) for n, s in status() if s != 'ok']
    for name, state in bad:
        print('%-50s %s' % (name, state))
    print('offline libraries: %d of %d in place' % (len(FILES) - len(bad), len(FILES)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
