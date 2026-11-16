# 아키텍처

```
브라우저 / Electron ──HTTP 127.0.0.1:47615──► app.py (Handler)
   index.html + web/*.js                         │
   Pixi + Live2D + MediaPipe                     ├─ chat_turn(): 대화 한 턴 (스트림, NDJSON)
                                                 ├─ system_prompt(): 기억, 기분, 모드로 프롬프트를 조립
                                                 ├─ generate/generate_stream(): luna.core.providers를 통한 신경망
                                                 └─ /act, /tts, /code/read, /doc/read … 경로 (모든 동작은 확인 카드 토큰으로)
```

## `luna/` 패키지

| 패키지 | 역할 | 규칙 |
|---|---|---|
| `luna/paths.py` | `DATA_DIR`(프로젝트 밖의 개인 데이터), `ROOT`, `migrate()` | 테스트에서는 항상 임시 폴더 |
| `luna/security.py` | Host/Origin, 토큰, CSP/헤더, `neutralize()` | 순수 함수, 의존성 없음 |
| `luna/core/` | `character`(기억, 기분, 일기), `memory_store`(의미 검색), `providers`, `feeling`(의미에 따른 어조), `episodes`(대화 기억), `replyfeel`(모델이 감정 태그를 달지 않았을 때, 루나의 말에 쓰인 단어로 감정을 추정), 클라우드 제공자를 통한 임베딩(`providers.embedder`, 설정의 체크박스, `memory_store.prefetch`), `catalog`(모델 라벨), `updater`(업데이트), `script`(답변 시나리오와 순수 텍스트 헬퍼), `models`, `voice`, `convo`, `lexicon`, `audit` | HTTP를 몰라요 |
| `luna/skills/` | 모델이 아니라 프로그램이 계산하는 것들: `dates`, `exact`, `lists`, `habits`, `reminders`, `stream`… | 스킬마다 4개 언어의 문장 분석과 정확한 답이 있어요 |
| `luna/senses/` | `hearing`, `localtts`(Windows 음성), `media`, `songid` | 로컬 처리만 |
| `luna/hands/` | `docfiles`, `codeedit`, `projects`, `runner`, `office`, `control`, `netsearch`… | 세상을 바꾸는 모든 것은 사용자가 확인 카드를 보고 누른 뒤에만 |
| `luna/dev/` | `devtools`, `engines`, `*_bridge`, `sqlrun`, `gitdiff`, `codescan`… | 확인 카드가 나오기 전에는 읽기만 |

## 핵심 아이디어

1. **프로그램이 결정하고, 모델은 제안해요.** 모델은 `[open:…]`, `[run:…]` 같은 명령을 쓰고, 서버는 이것을 토큰이 달린 확인 카드로 바꿔요. 동작은 사용자가 누른 뒤에만,
   그리고 바로 그 확인 카드를 위해 발급된 토큰으로만 실행돼요(`agent.take`, `*.take`). 토큰은 일회용이고 TTL이 있어요.
2. **오염(taint).** 한 턴에 "외부" 텍스트(인터넷, 문서, 코드 파일, 클립보드, SQL, diff)가 있었다면 `chat_turn`은 그 턴을 `tainted`로 봐요.
   스스로 열거나 실행하는 것은 아무것도 없어요. 클라이언트는 이런 읽기 뒤마다 `webRound`를 설정해요(`web/app.js`).
3. **정확한 계산은 프로그램에서.** 날짜, 퍼센트, 긴 숫자, 표는 코드(`luna/skills`)가 계산하고, 모델은 답을 말로 풀어낼 뿐이에요.
4. **기억.** `memory.json`(사용자와 그녀에 대한 사실, 일기, 기분)은 백업과 함께 보관해요. `character.recall()`은 단어 일치와 단어 형태로 사실을 고르고,
   `settings.json`에 `"embeddings": "ollama:nomic-embed-text"`가 있으면 의미로도 골라요(로컬 임베딩, SQLite 캐시).
5. **사용자 데이터는 코드와 분리해요**(`luna/paths.py`).

## 서버 구성

`app.py`(~800줄)는 실행과 주요 경로를 담당해요(`Handler`: `/act`, `/tts`, `/listen`, `/hear`, `/stream`, `/state`, `/chat`). 나머지는 따로 뺐어요.

| 파일 | 내용 |
|---|---|
| `luna/core/session.py` | `Session`과 `S` — 한 턴의 변경 가능한 상태(에이전트 모드, 언어, 카메라…). 전역 변수 아홉 개를 대신해요 |
| `luna/server/chat.py` | `chat_turn`, `open_item`, `end_task` — 채팅 엔진 |
| `luna/server/hands.py` | `HandsRoutes` — 손 경로(문서, 코드, 프로젝트, 명령, 엔진, 일기, 루나의 공간) |
| `luna/server/appref.py` | `_app()` — 실행 중인 `app`에 늦게 접근하는 함수로, 테스트가 `app.generate_stream`, `app.run_action` … 을 바꿔 끼울 수 있게 해요 |
| `luna/core/prompts.py`, `config.py`, `script.py`, `models.py` | 프롬프트 조립, 설정, 답변 시나리오, 모델 카탈로그 |

분리한 코드는 `from app import X`가 아니라 `_app().X`로 바꿔 끼울 수 있는 함수에 접근해요.
`chat_turn`은 여러 조각으로 나뉘어 있어요. `_turn_text`(그녀가 무엇을 답하는가), `_turn_hints`(프로그램이 그녀를 위해 계산하고 읽은 것), `_Got`(그녀가 답에서 요청한 모든 것), `_deliver`(그녀가 말을 마친 뒤의 처리: 표, 검색, 열기)예요. 함수 안에는 스트림이 남아 있고, `sentence`/`feed`/`commit`은 턴의 공유 상태를 감싼 클로저로 `test_chat_stream.py`의 테스트를 받아요.
