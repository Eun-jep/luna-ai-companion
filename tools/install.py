"""Installer of everything Luna needs on a new computer. Run it through install.bat (it also finds or installs Python first).
It never touches your data (memory, keys, journal, settings): it only installs programs and libraries and checks the files.
It speaks the language of Windows (English, Russian, Korean, Japanese); --lang xx forces one. It never installs Ollama: that is up to you.

HOW TO ADD A NEW REQUIREMENT LATER (so the next person gets it too):
  - a Python library:  add its name to requirements.txt (one per line). Nothing else to change.
  - an npm package:    add it to desktop/package.json. Nothing else to change.
  - a program:         add one line to PROGRAMS below (winget id) and, if it is needed to run, a check in main().
  - a file that must exist: add its path to FILES below.
  - a web address the page loads at start: add it to ONLINE below.
  - a message: add its key to every language of TEXT.
Run with --check to only look (changes nothing)."""
import ctypes
import importlib.metadata as md
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK_ONLY = '--check' in sys.argv
MIN_PYTHON = (3, 10)

# programs this project needs, installed with winget: (winget id, name)
PROGRAMS = {'node': ('OpenJS.NodeJS.LTS', 'Node.js')}
FILES = ['settings.json', 'index.html', 'app.py', 'web/app.js', 'web/stream.js', 'web/workspaces.js', 'web/chat-button.png', 'desktop/main.js', 'desktop/tray.png',
         'luna/paths.py', 'luna/security.py', 'luna/core/voice.py', 'luna/core/convo.py', 'luna/core/memory_store.py', 'luna/senses/media.py', 'luna/senses/hearing.py',
         'luna/hands/studio.py', 'luna/hands/runner.py', 'luna/hands/netsearch.py', 'luna/hands/docfiles.py', 'luna/hands/projects.py', 'luna/skills/stream.py',
         'tools/fetch_vendor.py']
ONLINE = ['https://cdnjs.cloudflare.com/ajax/libs/pixi.js/6.5.10/browser/pixi.min.js',
          'https://cdn.jsdelivr.net/npm/@pixi/unsafe-eval@6.5.10/dist/browser/unsafe-eval.min.js',
          'https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js',
          'https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/dist/cubism4.min.js']

TEXT = {
    'en': {
        'title': 'Luna: setup', 'check_only': ' (check only, nothing is changed)', 'python': '[Python]', 'libs': '[Python libraries]', 'node': '[Node.js and the Electron window]',
        'files': '[Project files]', 'vendor': '[Avatar libraries for offline work: web/vendor/]', 'online': '[Internet: the avatar libraries load when the page opens]',
        'ollama': '[Local AI, optional]',
        'py_ok': 'Python %d.%d.%d (%d.%d or newer is needed)', 'py_launcher': 'the "py" launcher was not found: start.bat runs the server through it (reinstall Python from python.org and keep the "py launcher" box ticked)',
        'no_winget': '     Automatic install is not available (no winget). Install %s yourself, then run install.bat again.',
        'winget': '     Installing %s with winget (Windows may ask for permission: press Yes)...',
        'installing': '     Installing: %s', 'pip_fail': '     pip could not download the libraries: check the internet, VPN, proxy or antivirus and run install.bat again.',
        'not_installed': 'not installed', 'npm_found': 'Node.js / npm found', 'npm_missing': 'Node.js / npm not found (without it the Electron window will not open; the browser version through start.bat works)',
        'electron_get': '     Installing Electron (about 100 MB, internet needed)...', 'electron_ok': 'Electron installed', 'electron_no': 'Electron not installed',
        'models': 'Live2D models in assets/models: %d', 'no_models': 'no Live2D models found: copy the assets\\models folder together with the project (there is no avatar without it)',
        'curl': 'curl.exe (a fallback for reading Wikipedia; it comes with Windows 10 and newer)',
        'vendor_ok': 'the libraries are in web/vendor/ (the page opens without the internet)', 'vendor_no': 'the libraries were not downloaded: the page will take them from the internet (run tools/fetch_vendor.py later)',
        'vendor_missing': 'tools/fetch_vendor.py not found', 'reachable': '%s is reachable', 'unreachable': '%s is not reachable (%s): the avatar cannot be drawn without it',
        'ollama_found': 'Ollama found: the app offers it in the settings when it is running',
        'ollama_note': 'Ollama is not installed. It is optional: install it yourself from https://ollama.com if you want a local AI, or paste a cloud AI key in the settings',
        'bad': ' Not everything is ready:', 'retry': ' Fix this and run install.bat again (it is safe: what is installed is left alone).',
        'done': ' All set.', 'run1': ' To start: double-click start-desktop.bat (desktop window) or start.bat (in the browser).',
        'run2': ' On first start choose an AI in the Settings and paste your key (or connect a local one).', 'run3': ' Memory, keys and journal are created by themselves and stay on this computer only.',
    },
    'ru': {
        'title': 'Луна: установка', 'check_only': ' (только проверка, ничего не меняется)', 'python': '[Python]', 'libs': '[Библиотеки Python]', 'node': '[Node.js и окно Electron]',
        'files': '[Файлы проекта]', 'vendor': '[Библиотеки аватара для работы без интернета: web/vendor/]', 'online': '[Интернет: библиотеки аватара грузятся при открытии страницы]',
        'ollama': '[Локальная нейросеть, по желанию]',
        'py_ok': 'Python %d.%d.%d (нужен %d.%d или новее)', 'py_launcher': 'лаунчер «py» не найден: start.bat запускает сервер через него (переустанови Python с python.org, оставив галку «py launcher»)',
        'no_winget': '     Автоустановка недоступна (нет winget). Поставь %s вручную, потом запусти install.bat ещё раз.',
        'winget': '     Устанавливаю %s через winget (может появиться окно Windows с вопросом «Разрешить?», нажми «Да»)...',
        'installing': '     Устанавливаю: %s', 'pip_fail': '     pip не смог скачать библиотеки: проверь интернет, VPN, прокси или антивирус и запусти install.bat ещё раз.',
        'not_installed': 'не установлена', 'npm_found': 'Node.js / npm найден', 'npm_missing': 'Node.js / npm не найден (без него не откроется окно Electron; веб-версия через start.bat работает)',
        'electron_get': '     Устанавливаю Electron (около 100 МБ, нужен интернет)...', 'electron_ok': 'Electron установлен', 'electron_no': 'Electron не установлен',
        'models': 'модели Live2D в assets/models: %d', 'no_models': 'модели Live2D не найдены: скопируй папку assets\\models вместе с проектом (без неё аватара не будет)',
        'curl': 'curl.exe (запасной путь для чтения Википедии; есть в Windows 10 и новее)',
        'vendor_ok': 'библиотеки лежат в web/vendor/ (страница открывается без интернета)', 'vendor_no': 'библиотеки не скачаны: страница возьмёт их из интернета (запусти tools/fetch_vendor.py позже)',
        'vendor_missing': 'tools/fetch_vendor.py не найден', 'reachable': '%s доступен', 'unreachable': '%s недоступен (%s): без него аватар не нарисуется',
        'ollama_found': 'Ollama найдена: приложение само предложит её в настройках, если она запущена',
        'ollama_note': 'Ollama не установлена. Это не обязательно: поставь её сам с https://ollama.com, если нужна локальная нейросеть, или вставь ключ облачной в настройках',
        'bad': ' Не всё готово:', 'retry': ' Исправь это и запусти install.bat ещё раз (он безопасен: уже установленное не трогает).',
        'done': ' Всё готово.', 'run1': ' Запуск: двойной щелчок по start-desktop.bat (окно-рабочий стол) или start.bat (в браузере).',
        'run2': ' При первом запуске в Настройках выбери нейросеть и вставь свой ключ (или подключи локальную).', 'run3': ' Память, ключи и журнал создаются сами и хранятся только на этом компьютере.',
    },
    'ko': {
        'title': '루나: 설치', 'check_only': ' (확인만 합니다. 아무것도 바뀌지 않아요)', 'python': '[Python]', 'libs': '[Python 라이브러리]', 'node': '[Node.js와 Electron 창]',
        'files': '[프로젝트 파일]', 'vendor': '[오프라인용 아바타 라이브러리: web/vendor/]', 'online': '[인터넷: 아바타 라이브러리는 페이지를 열 때 불러옵니다]',
        'ollama': '[로컬 AI, 선택 사항]',
        'py_ok': 'Python %d.%d.%d (%d.%d 이상 필요)', 'py_launcher': '"py" 런처를 찾지 못했어요. start.bat이 이것으로 서버를 실행합니다 (python.org에서 Python을 다시 설치하고 "py launcher"를 체크해 주세요)',
        'no_winget': '     자동 설치를 쓸 수 없어요 (winget 없음). %s을(를) 직접 설치한 뒤 install.bat을 다시 실행해 주세요.',
        'winget': '     winget으로 %s을(를) 설치하는 중 (Windows가 허용 여부를 물으면 "예"를 눌러 주세요)...',
        'installing': '     설치 중: %s', 'pip_fail': '     pip가 라이브러리를 내려받지 못했어요. 인터넷, VPN, 프록시, 백신을 확인하고 install.bat을 다시 실행해 주세요.',
        'not_installed': '설치되지 않음', 'npm_found': 'Node.js / npm 확인됨', 'npm_missing': 'Node.js / npm이 없어요 (없으면 Electron 창이 열리지 않아요. start.bat의 브라우저 버전은 동작합니다)',
        'electron_get': '     Electron 설치 중 (약 100MB, 인터넷 필요)...', 'electron_ok': 'Electron 설치됨', 'electron_no': 'Electron이 설치되지 않음',
        'models': 'assets/models의 Live2D 모델: %d개', 'no_models': 'Live2D 모델이 없어요. assets\\models 폴더를 프로젝트와 함께 복사해 주세요 (없으면 아바타가 나오지 않아요)',
        'curl': 'curl.exe (위키백과 읽기용 대체 경로, Windows 10 이상에 포함)',
        'vendor_ok': '라이브러리가 web/vendor/에 있어요 (인터넷 없이도 페이지가 열려요)', 'vendor_no': '라이브러리를 받지 못했어요. 페이지가 인터넷에서 불러옵니다 (나중에 tools/fetch_vendor.py 실행)',
        'vendor_missing': 'tools/fetch_vendor.py를 찾을 수 없어요', 'reachable': '%s 접속 가능', 'unreachable': '%s 접속 불가 (%s): 없으면 아바타를 그릴 수 없어요',
        'ollama_found': 'Ollama 확인됨: 실행 중이면 앱이 설정에서 제안해 줘요',
        'ollama_note': 'Ollama가 설치되어 있지 않아요. 선택 사항입니다. 로컬 AI가 필요하면 https://ollama.com 에서 직접 설치하거나, 설정에 클라우드 AI 키를 붙여 넣으세요',
        'bad': ' 아직 준비되지 않은 항목:', 'retry': ' 문제를 해결한 뒤 install.bat을 다시 실행해 주세요 (이미 설치된 것은 건드리지 않아요).',
        'done': ' 준비 완료.', 'run1': ' 시작: start-desktop.bat(데스크톱 창) 또는 start.bat(브라우저)을 더블클릭하세요.',
        'run2': ' 처음 실행하면 설정에서 AI를 고르고 키를 붙여 넣으세요 (또는 로컬 AI 연결).', 'run3': ' 기억, 키, 기록은 자동으로 만들어지고 이 컴퓨터에만 저장돼요.',
    },
    'ja': {
        'title': 'ルナ: セットアップ', 'check_only': '（確認のみ。何も変更しません）', 'python': '[Python]', 'libs': '[Python ライブラリ]', 'node': '[Node.js と Electron ウィンドウ]',
        'files': '[プロジェクトのファイル]', 'vendor': '[オフライン用アバターライブラリ: web/vendor/]', 'online': '[インターネット: アバターのライブラリはページを開くときに読み込まれます]',
        'ollama': '[ローカルAI（任意）]',
        'py_ok': 'Python %d.%d.%d（%d.%d 以上が必要）', 'py_launcher': '「py」ランチャーが見つかりません。start.bat がこれでサーバーを起動します（python.org から Python を入れ直し、「py launcher」にチェックを入れてください）',
        'no_winget': '     自動インストールは使えません（winget がありません）。%s を手動でインストールしてから、もう一度 install.bat を実行してください。',
        'winget': '     winget で %s をインストール中（Windows が許可を求めたら「はい」を押してください）...',
        'installing': '     インストール中: %s', 'pip_fail': '     pip がライブラリを取得できませんでした。インターネット、VPN、プロキシ、ウイルス対策を確認して install.bat をもう一度実行してください。',
        'not_installed': '未インストール', 'npm_found': 'Node.js / npm が見つかりました', 'npm_missing': 'Node.js / npm が見つかりません（ないと Electron ウィンドウは開きません。start.bat のブラウザ版は動きます）',
        'electron_get': '     Electron をインストール中（約100MB、インターネットが必要）...', 'electron_ok': 'Electron はインストール済み', 'electron_no': 'Electron は未インストール',
        'models': 'assets/models の Live2D モデル: %d 個', 'no_models': 'Live2D モデルが見つかりません。assets\\models フォルダをプロジェクトと一緒にコピーしてください（ないとアバターが出ません）',
        'curl': 'curl.exe（Wikipedia 読み取りの予備経路。Windows 10 以降に付属）',
        'vendor_ok': 'ライブラリは web/vendor/ にあります（インターネットなしでもページが開きます）', 'vendor_no': 'ライブラリを取得できませんでした。ページはインターネットから読み込みます（後で tools/fetch_vendor.py を実行）',
        'vendor_missing': 'tools/fetch_vendor.py が見つかりません', 'reachable': '%s に接続できます', 'unreachable': '%s に接続できません（%s）: ないとアバターを描画できません',
        'ollama_found': 'Ollama が見つかりました。起動していれば設定で提案されます',
        'ollama_note': 'Ollama はインストールされていません。任意です。ローカルAIが必要なら https://ollama.com から自分でインストールするか、設定にクラウドAIのキーを貼り付けてください',
        'bad': ' まだ整っていない項目:', 'retry': ' 解決してから install.bat をもう一度実行してください（インストール済みのものには触れません）。',
        'done': ' 準備完了。', 'run1': ' 起動: start-desktop.bat（デスクトップウィンドウ）または start.bat（ブラウザ）をダブルクリック。',
        'run2': ' 初回起動時は設定でAIを選び、キーを貼り付けてください（またはローカルAIに接続）。', 'run3': ' 記憶・キー・ジャーナルは自動で作られ、このコンピューターにだけ保存されます。',
    },
}
OK_MARK = {'en': 'OK', 'ru': 'ОК', 'ko': 'OK', 'ja': 'OK'}


def detect_language():
    """--lang xx, else the Windows display language (English when it is none of ours)."""
    for i, arg in enumerate(sys.argv):
        if arg == '--lang' and i + 1 < len(sys.argv) and sys.argv[i + 1] in TEXT:
            return sys.argv[i + 1]
        if arg.startswith('--lang=') and arg[7:] in TEXT:
            return arg[7:]
    try:
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x19: 'ru', 0x12: 'ko', 0x11: 'ja'}.get(primary, 'en')
    except (AttributeError, OSError):
        return 'en'


LANG = detect_language()


def tr(key, *args):
    text = TEXT[LANG].get(key) or TEXT['en'][key]
    return text % args if args else text


results = []   # (ok, required, text)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):
    pass


def say(text=''):
    print(text, flush=True)


def report(ok, text, required=True):
    results.append((ok, required, text))
    say(('  [%s]  ' % OK_MARK[LANG] if ok else '  [!!]  ' if required else '  [--]  ') + text)
    return ok


def run(cmd, cwd=None, quiet=False):
    """Run a command, showing its output unless quiet. Returns the exit code (127 when the program is missing)."""
    try:
        return subprocess.run(cmd, cwd=cwd, stdout=subprocess.DEVNULL if quiet else None,
                              stderr=subprocess.DEVNULL if quiet else None).returncode
    except OSError:
        return 127


def add_to_path(*dirs):
    for d in dirs:
        if d and os.path.isdir(d) and d.lower() not in os.environ['PATH'].lower():
            os.environ['PATH'] = d + os.pathsep + os.environ['PATH']


def refresh_path():
    """Programs installed a moment ago are not yet on this window's PATH: add their usual folders."""
    add_to_path(os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'nodejs'))


def winget(pid, name):
    if not shutil.which('winget'):
        say(tr('no_winget', name))
        return False
    say(tr('winget', name))
    code = run(['winget', 'install', '-e', '--id', pid, '--silent', '--accept-package-agreements', '--accept-source-agreements'])
    refresh_path()
    return code in (0, -1978335189)   # -1978335189: already installed / no newer version


def requirement_names():
    names = []
    for line in (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines():
        line = line.split('#')[0].strip()
        if line:
            names.append(re.split(r'[<>=!~\[; ]', line, maxsplit=1)[0])
    return names


def installed(name):
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None


def step_python():
    v = sys.version_info
    report((v.major, v.minor) >= MIN_PYTHON, tr('py_ok', v.major, v.minor, v.micro, *MIN_PYTHON))
    if shutil.which('py') is None:
        report(False, tr('py_launcher'), False)


def step_libraries():
    say('\n' + tr('libs'))
    names = requirement_names()
    missing = [n for n in names if not installed(n)]
    if missing and not CHECK_ONLY:
        say(tr('installing', ', '.join(missing)))
        code = run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(ROOT / 'requirements.txt')])
        if code:
            say(tr('pip_fail'))
    for n in names:
        v = installed(n)
        report(bool(v), '%s %s' % (n, v or tr('not_installed')))


def step_node():
    say('\n' + tr('node'))
    refresh_path()
    if not shutil.which('npm') and not CHECK_ONLY:
        winget(*PROGRAMS['node'])
    npm = shutil.which('npm')
    report(bool(npm), tr('npm_found') if npm else tr('npm_missing'))
    electron = ROOT / 'desktop' / 'node_modules' / 'electron' / 'dist'
    if npm and not electron.is_dir() and not CHECK_ONLY:
        say(tr('electron_get'))
        run([npm, 'install', '--no-audit', '--no-fund'], cwd=str(ROOT / 'desktop'))
    report(electron.is_dir(), tr('electron_ok') if electron.is_dir() else tr('electron_no'), bool(npm))


def step_files():
    say('\n' + tr('files'))
    for rel in FILES:
        report((ROOT / rel).is_file(), rel)
    models = list((ROOT / 'assets' / 'models').glob('*/*.model3.json')) + list((ROOT / 'assets' / 'models').glob('*/*/*.model3.json'))
    report(bool(models), tr('models', len(models)) if models else tr('no_models'))
    report(shutil.which('curl') is not None, tr('curl'), False)


def step_vendor():
    say('\n' + tr('vendor'))
    script = ROOT / 'tools' / 'fetch_vendor.py'
    if not script.is_file():
        report(False, tr('vendor_missing'), False)
        return
    code = run([sys.executable, str(script)] + (['--check'] if CHECK_ONLY else []), quiet=True)
    report(code == 0, tr('vendor_ok') if code == 0 else tr('vendor_no'), False)


def step_online():
    say('\n' + tr('online'))
    for url in ONLINE:
        try:
            urllib.request.urlopen(urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'LunaInstaller'}), timeout=10).close()
            report(True, tr('reachable', url.split('/')[2]))
        except Exception as exc:
            report(False, tr('unreachable', url.split('/')[2], type(exc).__name__))


def step_ollama():
    """Only tells. Ollama is never installed from here: whoever wants a local AI installs it themselves."""
    say('\n' + tr('ollama'))
    refresh_path()
    found = shutil.which('ollama') or any(os.path.exists(os.path.expandvars(p)) for p in (r'%LOCALAPPDATA%\Programs\Ollama\ollama.exe', r'%ProgramFiles%\Ollama\ollama.exe'))
    report(bool(found), tr('ollama_found') if found else tr('ollama_note'), False)


def main():
    say('=' * 60)
    say(' ' + tr('title') + (tr('check_only') if CHECK_ONLY else ''))
    say('=' * 60)
    say('\n' + tr('python'))
    step_python()
    step_libraries()
    step_node()
    step_files()
    step_vendor()
    step_online()
    step_ollama()
    bad = [t for ok, req, t in results if not ok and req]
    say('\n' + '=' * 60)
    if bad:
        say(tr('bad'))
        for t in bad:
            say('   - ' + t)
        say(tr('retry'))
    else:
        say(tr('done'))
        say(tr('run1'))
        say(tr('run2'))
        say(tr('run3'))
    say('=' * 60)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
