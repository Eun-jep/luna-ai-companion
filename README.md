# Луна / Luna — локальный компаньон с Live2D-аватаром

**RU.** Луна — персонаж с анимированным аватаром (Live2D), которым управляет нейросеть: она разговаривает голосом, видит камеру и экран (по разрешению),
помнит собеседника, помогает с кодом, документами и играми. Сервер — на чистой стандартной библиотеке Python, слушает только `127.0.0.1`.

**EN.** Luna is a local companion: a Live2D avatar driven by a language model. She talks (edge-tts), can see the webcam and the screen when allowed, remembers
the person she talks to, and helps with code, documents and game engines. The server uses only the Python standard library and listens on `127.0.0.1` only.

## Быстрый старт / Quick start

```bash
install.bat            # один раз: Python-библиотеки, Electron, офлайн-библиотеки аватара (web/vendor/)
start.bat              # в браузере (Chrome/Edge)
start-desktop.bat      # окно-рабочий стол (Electron)
```

Нейросеть выбирается в **Настройках → Нейросеть** (Z.ai, OpenAI, Anthropic, Gemini, OpenRouter или локальные Ollama / LM Studio / Jan / llama.cpp).
Ключи хранятся зашифрованными (Windows DPAPI). Модели Live2D кладутся в `assets/models/` (в репозиторий они не входят).

## Где лежат данные / Where your data lives

Память, ключи, журнал, песни и настройки окна — **не в папке проекта**, а в `%APPDATA%\Luna` (или `~/.luna`; папку можно задать переменной `LUNA_DATA_DIR`).
Данные от старой версии переносятся туда автоматически при первом запуске, ничего не перезаписывается.

## Структура / Layout

| Путь | Что там |
|---|---|
| `app.py` | запуск: HTTP-сервер, чат-движок, маршруты |
| `luna/core/` | характер и память, провайдеры нейросетей, голос, сценарий ответа, журнал |
| `luna/skills/` | навыки, считаемые программой: даты, арифметика, списки, привычки, напоминания, стример… |
| `luna/senses/` | слух (динамики), «что на экране» по заголовку окна, определение песни |
| `luna/hands/` | руки: документы, код, проекты, команды, мышь и клавиатура, интернет |
| `luna/dev/` | разработчик: движки, Unreal/Unity/Godot, SQL, git-diff, аудит проекта, логи |
| `web/`, `index.html` | страница (JS/CSS), `web/vendor/` — скачанные библиотеки (не в git) |
| `desktop/` | оболочка Electron |
| `tools/` | установщик, очистка, загрузка офлайн-библиотек |
| `tests/` | тесты (pytest + старые скрипты) |
| `docs/` | `FEATURES.txt` (полная справка), `ARCHITECTURE.md`, `SECURITY.md`, `DEVELOPMENT.md` |

## Разработка / Development

```bash
py -m venv .venv && .venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest tests/native -n 4     # все тесты (~3 мин)
.venv\Scripts\python -m ruff check .                  # линтер
.venv\Scripts\python -m mypy                          # типы (новые модули)
```

Подробнее: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/SECURITY.md](docs/SECURITY.md), [CHANGELOG.md](CHANGELOG.md).
Полная справка по возможностям (русский): [docs/FEATURES.txt](docs/FEATURES.txt).
