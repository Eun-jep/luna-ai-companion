# Разработка

## Окружение

```bash
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt     # requirements.txt + pytest, xdist, ruff, mypy
.venv\Scripts\python tools\fetch_vendor.py                       # офлайн-библиотеки страницы (web/vendor/, не в git)
```

`requirements.txt` — минимальные версии (`>=`), `requirements.lock` — точные версии, на которых прошли тесты.

## Тесты

```bash
.venv\Scripts\python -m pytest tests/native -n 4          # всё: новые pytest-тесты + старые скрипты (по процессу на файл, ~3 мин)
.venv\Scripts\python -m pytest tests/native -m "not slow"  # только быстрые pytest-тесты
.venv\Scripts\python tests\run_all.py                      # старый запуск, один файл за другим
.venv\Scripts\python -X utf8 tests\test_dates.py           # один старый тест
```

- Старые `tests/test_*.py` — скрипты: печатают `PASS`/`FAIL`, оценивает их `tests/native/test_legacy_scripts.py`.
- `tests/legacy_counts.json` — сколько проверок (`PASS`) печатает каждый старый скрипт. Если скрипт стал печатать меньше (проверки молча пропали), тест падает.
  Добавили или убрали проверки намеренно — `python tools/legacy_counts.py` перезапишет файл (он отказывается, если хоть один скрипт не проходит).
- Тесты **никогда** не трогают настоящие данные: `luna/paths.py` в тестах выбирает временную папку. Не открывайте в тестах `%APPDATA%\Luna`.
- Старые тесты поднимают HTTP-сервер на фиксированном порту: у каждого файла свой порт (88xx/89xx), иначе параллельный запуск падает.
- Подмена в тестах — через атрибут модуля (`app.generate_stream = fake`); код должен вызывать такие функции через модуль, а не через `from x import f` до подмены.

## Обновления

- Версия живёт в `luna/__init__.py` и должна совпадать с `pyproject.toml` (проверяет `tests/native/test_updater.py`).
- Пакет обновления — zip с файлами программы по их путям (`luna/…`, `web/…`, `app.py`…). Канал: `{"version", "url", "sha256", "notes"}`, `sha256 = hashlib.sha256(zip).hexdigest()`.
  Версия в `luna/__init__.py` внутри пакета обязана совпасть с версией канала. Что разрешено заменять — `ALLOWED`/`NEVER` в `luna/core/updater.py`.

## Стиль и проверки

```bash
.venv\Scripts\python -m ruff check .     # E/W/F и выборочные B/S (настройки в pyproject.toml)
.venv\Scripts\python -m mypy             # типы для luna/paths.py, luna/security.py, luna/core/memory_store.py
```

## Как добавить навык

1. Модуль в `luna/skills/` (разбор фразы на ru/en/ko/ja — слова держим в `luna/core/lexicon.py`; ответ считает код).
2. Подключить в `chat_turn` (`luna/server/chat.py`) рядом с похожими навыками; текст «снаружи» — через `security.neutralize` и с `webRound`.
3. Тест в `tests/native/` (pytest) — старый скриптовый формат только для поддержки существующих файлов.
4. Строка в `docs/FEATURES.txt` и запись в `CHANGELOG.md`.

## Личные данные при разработке

Хотите запустить сервер на пустых данных: `set LUNA_DATA_DIR=C:\temp\luna-dev`. Осторожно: при запуске `app.py` с `LUNA_DATA_DIR` старые файлы
рядом с программой (если они ещё там) переносятся в эту папку.

- Сквозной тест страницы (`tests/native/test_e2e_page.py`): настоящая страница в Edge через Playwright, подменена только модель. Пропускается, если нет Playwright/Edge. Файл закреплён за одним процессом xdist (`xdist_group`); ждать условий на странице через `wait_until`, а не `wait_for_function("строка")` (CSP запрещает eval).
