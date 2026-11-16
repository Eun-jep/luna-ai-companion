# 개발

## 환경

```bash
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt     # requirements.txt + pytest, xdist, ruff, mypy
.venv\Scripts\python tools\fetch_vendor.py                       # 페이지용 오프라인 라이브러리 (web/vendor/, git에 포함되지 않음)
```

`requirements.txt`는 최소 버전(`>=`)이고, `requirements.lock`은 테스트를 통과한 정확한 버전이에요.

## 테스트

```bash
.venv\Scripts\python -m pytest tests/native -n 4          # 전부: 새 pytest 테스트 + 옛 스크립트 (파일당 프로세스 하나, ~3분)
.venv\Scripts\python -m pytest tests/native -m "not slow"  # 빠른 pytest 테스트만
.venv\Scripts\python tests\run_all.py                      # 옛 실행 방식, 파일을 차례로 하나씩
.venv\Scripts\python -X utf8 tests\test_dates.py           # 옛 테스트 하나
```

- 옛 `tests/test_*.py`는 스크립트예요. `PASS`/`FAIL`을 출력하고, `tests/native/test_legacy_scripts.py`가 이를 판정해요.
- `tests/legacy_counts.json`에는 옛 스크립트가 각각 몇 개의 검사(`PASS`)를 출력하는지 들어 있어요. 스크립트가 더 적게 출력하면(검사가 조용히 사라졌다면) 테스트가 실패해요.
  검사를 일부러 추가하거나 뺐다면 `python tools/legacy_counts.py`가 파일을 다시 써요(스크립트가 하나라도 통과하지 못하면 거부해요).
- 테스트는 실제 데이터를 **절대** 건드리지 않아요. 테스트에서는 `luna/paths.py`가 임시 폴더를 골라요. 테스트에서 `%APPDATA%\Luna`를 열지 마세요.
- 옛 테스트는 고정 포트에서 HTTP 서버를 띄워요. 파일마다 포트가 달라야 해요(88xx/89xx). 그렇지 않으면 병렬 실행이 실패해요.
- 테스트에서의 대체는 모듈 속성으로 해요(`app.generate_stream = fake`). 코드는 이런 함수를 대체 전에 `from x import f`로 가져오지 말고 모듈을 통해 호출해야 해요.

## 업데이트

- 버전은 `luna/__init__.py`에 있고 `pyproject.toml`과 일치해야 해요(`tests/native/test_updater.py`가 확인해요).
- 업데이트 패키지는 프로그램 파일을 경로 그대로(`luna/…`, `web/…`, `app.py`…) 담은 zip이에요. 채널: `{"version", "url", "sha256", "notes"}`, `sha256 = hashlib.sha256(zip).hexdigest()`.
  패키지 안 `luna/__init__.py`의 버전은 채널의 버전과 반드시 같아야 해요. 교체를 허용하는 대상은 `luna/core/updater.py`의 `ALLOWED`/`NEVER`예요.

## 스타일과 검사

```bash
.venv\Scripts\python -m ruff check .     # E/W/F와 일부 B/S (설정은 pyproject.toml)
.venv\Scripts\python -m mypy             # luna/paths.py, luna/security.py, luna/core/memory_store.py의 타입
```

## 스킬 추가하는 방법

1. `luna/skills/`에 모듈을 만들어요(문장 분석은 ru/en/ko/ja로, 단어는 `luna/core/lexicon.py`에 두고, 답은 코드가 계산해요).
2. `chat_turn`(`luna/server/chat.py`)에서 비슷한 스킬 옆에 연결해요. "외부" 텍스트는 `security.neutralize`를 거치고 `webRound`를 붙여요.
3. `tests/native/`에 테스트(pytest)를 추가해요. 옛 스크립트 형식은 기존 파일을 유지할 때만 써요.
4. `docs/FEATURES.txt`에 한 줄을 추가하고 `CHANGELOG.md`에 기록해요.

## 개발 중의 개인 데이터

빈 데이터로 서버를 실행하고 싶다면 `set LUNA_DATA_DIR=C:\temp\luna-dev`를 쓰세요. 주의: `LUNA_DATA_DIR`를 지정하고 `app.py`를 실행하면, 프로그램 옆에 (아직 있다면) 남아 있는 옛 파일이
이 폴더로 옮겨져요.

- 페이지 엔드투엔드 테스트(`tests/native/test_e2e_page.py`): Playwright로 Edge에서 실제 페이지를 열고, 모델만 바꿔 끼워요. Playwright나 Edge가 없으면 건너뛰어요. Electron 셸은 테스트가 다루지 않아요(실제 화면이 필요해요). 로그는 `%APPDATA%\Luna\shell.log`이고, `.venv`에서의 실행 확인은 정적으로 `test_deps.py`에 있어요. 이 파일은 xdist 프로세스 하나에 고정돼 있어요(`xdist_group`). 페이지의 조건은 `wait_for_function("문자열")`이 아니라 `wait_until`로 기다려요(CSP가 eval을 막아요).
