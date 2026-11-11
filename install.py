"""Installer of everything Luna needs on a new computer. Run it through install.bat (it also finds or installs Python first).
It never touches your data (memory, keys, journal, settings): it only installs programs and libraries and checks the files.

HOW TO ADD A NEW REQUIREMENT LATER (so the next person gets it too):
  - a Python library:  add its name to requirements.txt (one per line). Nothing else to change.
  - an npm package:    add it to desktop/package.json. Nothing else to change.
  - a program:         add one line to PROGRAMS below (winget id) and, if it is needed to run, a check in main().
  - a file that must exist: add its path to FILES below.
  - a web address the page loads at start: add it to ONLINE below.
Run with --check to only look (changes nothing)."""
import importlib.metadata as md
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHECK_ONLY = '--check' in sys.argv
ASK_OLLAMA = '--ollama' in sys.argv
NO_OLLAMA = '--no-ollama' in sys.argv

# programs this project can use, installed with winget: (winget id, name, required?)
PROGRAMS = {
    'node': ('OpenJS.NodeJS.LTS', 'Node.js (нужен для окна Electron)', True),
    'ollama': ('Ollama.Ollama', 'Ollama (локальная нейросеть, по желанию)', False),
}
FILES = [('settings.json', 'настройки персонажа'), ('index.html', 'страница'), ('app.py', 'сервер'), ('web/app.js', 'скрипты страницы'),
         ('web/chat-button.png', 'картинка свёрнутого чата'), ('desktop/main.js', 'окно Electron'), ('desktop/tray.png', 'значок в трее'),
         ('voice.py', 'интонация голоса'), ('media.py', 'что она видит на экране по названию окна'),
         ('hearing.py', 'слух: что играет в динамиках'), ('studio.py', 'библиотека песен'), ('runner.py', 'запуск команд разработчика'), ('netsearch.py', 'интернет: поиск и чтение страниц'), ('docfiles.py', 'документы и папки'), ('convo.py', 'умный собеседник'), ('stream.py', 'режим стримера'), ('projects.py', 'создание проектов'), ('web/stream.js', 'страница стримера'), ('web/workspaces.js', 'папки для проектов'),
         ('paths.py', 'где лежат данные пользователя'), ('security.py', 'защита локального сервера'), ('memory_store.py', 'поиск воспоминаний по смыслу'), ('tools/fetch_vendor.py', 'загрузка библиотек для работы без интернета')]
ONLINE = ['https://cdnjs.cloudflare.com/ajax/libs/pixi.js/6.5.10/browser/pixi.min.js',
          'https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js',
          'https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/dist/cubism4.min.js']
MIN_PYTHON = (3, 10)

results = []   # (ok, required, text)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):
    pass


def say(text=''):
    print(text, flush=True)


def report(ok, text, required=True):
    results.append((ok, required, text))
    say(('  [ОК]  ' if ok else '  [!!]  ' if required else '  [--]  ') + text)
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
    pf = os.environ.get('ProgramFiles', r'C:\Program Files')
    local = os.environ.get('LOCALAPPDATA', '')
    add_to_path(os.path.join(pf, 'nodejs'), os.path.join(local, 'Programs', 'Ollama'), os.path.join(pf, 'Ollama'))


def winget(pid, name):
    if not shutil.which('winget'):
        say('     Автоустановка недоступна (нет winget). Поставь %s вручную, потом запусти install.bat ещё раз.' % name)
        return False
    say('     Устанавливаю %s через winget (может появиться окно Windows с вопросом «Разрешить?», нажми «Да»)...' % name)
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
    ok = (v.major, v.minor) >= MIN_PYTHON
    report(ok, 'Python %d.%d.%d (нужен %d.%d или новее)' % (v.major, v.minor, v.micro, *MIN_PYTHON))
    if shutil.which('py') is None:
        report(False, 'лаунчер «py» не найден: start.bat запускает сервер через него (переустанови Python с python.org, оставив галку «py launcher»)', False)


def step_libraries():
    say('\n[Библиотеки Python]')
    names = requirement_names()
    missing = [n for n in names if not installed(n)]
    if missing and not CHECK_ONLY:
        say('     Устанавливаю: %s' % ', '.join(missing))
        code = run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(ROOT / 'requirements.txt')])
        if code:
            say('     pip не смог скачать библиотеки: проверь интернет, VPN, прокси или антивирус и запусти install.bat ещё раз.')
    for n in names:
        v = installed(n)
        report(bool(v), '%s %s' % (n, v or 'не установлена'))


def step_node():
    say('\n[Node.js и окно Electron]')
    refresh_path()
    if not shutil.which('npm') and not CHECK_ONLY:
        winget(*PROGRAMS['node'][:2])
    npm = shutil.which('npm')
    report(bool(npm), 'Node.js / npm ' + ('найден' if npm else 'не найден (без него не откроется окно Electron; веб-версия через start.bat работает)'))
    electron = ROOT / 'desktop' / 'node_modules' / 'electron' / 'dist'
    if npm and not electron.is_dir() and not CHECK_ONLY:
        say('     Устанавливаю Electron (около 100 МБ, нужен интернет)...')
        run([npm, 'install', '--no-audit', '--no-fund'], cwd=str(ROOT / 'desktop'))
    report(electron.is_dir(), 'Electron ' + ('установлен' if electron.is_dir() else 'не установлен'), bool(npm))


def step_files():
    say('\n[Файлы проекта]')
    for rel, what in FILES:
        report((ROOT / rel).is_file(), '%s (%s)' % (rel, what))
    models = list((ROOT / 'assets' / 'models').glob('*/*.model3.json')) + list((ROOT / 'assets' / 'models').glob('*/*/*.model3.json'))
    report(bool(models), 'модели Live2D в assets/models: %d' % len(models) if models else
           'модели Live2D не найдены: скопируй папку assets\\models вместе с проектом (без неё аватара не будет)')
    report(shutil.which('curl') is not None, 'curl.exe (запасной путь для чтения Википедии; есть в Windows 10 и новее)', False)


def step_vendor():
    say('\n[Библиотеки аватара для работы без интернета: web/vendor/]')
    script = ROOT / 'tools' / 'fetch_vendor.py'
    if not script.is_file():
        report(False, 'tools/fetch_vendor.py не найден', False)
        return
    code = run([sys.executable, str(script)] + (['--check'] if CHECK_ONLY else []), quiet=True)
    report(code == 0, 'библиотеки лежат в web/vendor/ (страница открывается без интернета)' if code == 0 else
           'библиотеки не скачаны: страница возьмёт их из интернета (запусти tools/fetch_vendor.py позже)', False)


def step_online():
    say('\n[Интернет: библиотеки аватара грузятся при открытии страницы]')
    for url in ONLINE:
        try:
            urllib.request.urlopen(urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'LunaInstaller'}), timeout=10).close()
            report(True, url.split('/')[2] + ' доступен')
        except Exception as exc:
            report(False, '%s недоступен (%s): без него аватар не нарисуется' % (url.split('/')[2], type(exc).__name__))


def step_ollama():
    say('\n[Локальная нейросеть, по желанию]')
    refresh_path()
    if shutil.which('ollama'):
        report(True, 'Ollama найдена: приложение само предложит её в настройках, если она запущена', False)
        return
    want = ASK_OLLAMA
    if not want and not NO_OLLAMA and not CHECK_ONLY and sys.stdin.isatty():
        say('     Ollama позволяет Луне думать на самом компьютере, без интернета и ключей (нужна видеокарта или терпение).')
        want = input('     Установить Ollama сейчас? [y/N] ').strip().lower() in ('y', 'yes', 'д', 'да')
    if want and not CHECK_ONLY:
        winget(*PROGRAMS['ollama'][:2])
        report(bool(shutil.which('ollama')), 'Ollama ' + ('установлена. Скачай модель командой «ollama pull llama3.2»' if shutil.which('ollama') else 'не установилась'), False)
    else:
        report(False, 'Ollama не установлена (не обязательно: можно использовать ключ облачной нейросети в настройках)', False)


def main():
    say('=' * 60)
    say(' Луна: установка' + (' (только проверка, ничего не меняется)' if CHECK_ONLY else ''))
    say('=' * 60)
    say('\n[Python]')
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
        say(' Не всё готово:')
        for t in bad:
            say('   - ' + t)
        say(' Исправь это и запусти install.bat ещё раз (он безопасен: уже установленное не трогает).')
    else:
        say(' Всё готово.')
        say(' Запуск: двойной щелчок по start-desktop.bat (окно-рабочий стол) или start.bat (в браузере).')
        say(' При первом запуске в Настройках выбери нейросеть и вставь свой ключ (или подключи локальную).')
        say(' Память, ключи и журнал создаются сами и хранятся только на этом компьютере.')
    say('=' * 60)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
