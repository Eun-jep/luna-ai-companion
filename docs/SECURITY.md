# 보안

## 위협 모델

서버는 `127.0.0.1:47615`에서 열려요. 위협은 다음과 같아요. (1) 사용자의 브라우저에 열린 다른 웹 페이지(DNS rebinding, CSRF), (2) 루나가 읽는 "외부" 텍스트(웹사이트, 문서, 파일, 클립보드)에 숨겨진 명령, (3) 개인 데이터와 키 유출, (4) 사용자 파일 손상.

## 적용한 대책

| 위협 | 방어 |
|---|---|
| DNS rebinding / 낯선 Origin | `Handler.guard()`: `Host`는 `127.0.0.1\|localhost\|[::1]:포트`여야 하고, `Origin`은 우리 것만 허용해요(`luna/security.py`). 그 외에는 403 |
| 토큰 추측 | 세션 토큰(`secrets.token_urlsafe(32)`)을 `hmac.compare_digest`로 비교해요. 페이지는 `/`와 `/growth`에서만 토큰을 받아요 |
| XSS, 프레임, Referer 유출 | `unsafe-inline`과 `unsafe-eval`이 없는 CSP(자체 스크립트만 쓰고, 유일한 인라인 스크립트에는 응답마다 일회용 `nonce`를 붙여요. CDN 예비 주소, `object-src 'none'`, `frame-ancestors 'none'`), `X-Frame-Options`, `Referrer-Policy`, `nosniff`, CORP/COOP |
| 외부 텍스트 속 명령 | 파일, 문서, diff, 인터넷에는 `security.neutralize()`를 적용해요(`<<<`/``` 경계, 위조된 역할 태그). 이런 읽기 뒤에는 `webRound=2`가 걸리고, 동작은 확인 카드와 클릭이 있어야만 실행돼요 |
| 키 | `keys.dat`는 Windows DPAPI로 암호화해요. 페이지에는 마지막 4글자만 보여요. 파일은 프로젝트 밖에 있고 `.gitignore`에 들어 있어요 |
| 개인 데이터 | `%APPDATA%\Luna`에 두고 프로젝트 폴더에는 두지 않아요. 테스트는 항상 임시 폴더에서 동작해요 |
| 개발자 명령 | 확인 카드와 클릭이 있어야만, 고정된 도구 목록에서, 셸 없이 실행돼요. Windows Job Object(`luna/hands/sandbox.py`) 안에서 실행하며, 타임아웃이나 종료 뒤에는 프로세스 트리 전체를 종료해요. 프로세스 수(128)와 메모리(8GB)에 제한이 있고, 클립보드와 시스템 설정에는 접근할 수 없으며, 출력은 제한을 두고 읽어요. 환경에는 키/토큰/비밀번호/cookie/DSN이 없어요. 디스크 루트, 홈 폴더, 시스템 폴더에서는 실행하지 않아요 |
| 사용자 파일 | 확인 카드 뒤에만 쓰고, 백업은 `edit_backups`에, 동작 기록(`audit`)은 되돌리기를 지원해요 |
| 서드파티 라이브러리 | `tools/fetch_vendor.py`가 `web/vendor/`로 내려받고 SHA-256을 대조해요. 페이지는 로컬 사본을 써요(오프라인에서도 동작) |
| 임베딩 | Ollama의 loopback 주소만 써요. 기억은 컴퓨터 밖으로 나가지 않아요 |

## 알려진 한계

- 업데이트(`luna/core/updater.py`)는 **서명되지 않아요**. SHA-256이 패키지와 같은 채널에서 오기 때문에, 손상이나 혼동은 막아 주지만 악의적인 채널 소유자는 막지 못해요
  (Python 표준 라이브러리에는 공개키 서명 검증이 없어요). `update_feed`에는 신뢰하는 채널만 지정하세요. 패키지 서명은 설치 프로그램 서명과 함께 풀어야 할 과제예요.

- CSP에 `'wasm-unsafe-eval'`이 남아 있어요(MediaPipe와 Live2D Core가 WebAssembly 때문에 필요해요). 일반 `eval`과 인라인 스크립트/스타일은 없어요.
  Pixi 6은 `web/vendor/unsafe-eval.min.js`(`@pixi/unsafe-eval`, MIT, SHA-256으로 고정) 덕분에 `eval` 없이 동작해요. 이 라이브러리가 `web/vendor/`에 없으면 페이지가 CDN에서 가져와요.
  페이지는 외부 HTML을 보여 주지 않아요. Electron 셸이 페이지에 넣는 것(`executeJavaScript`, `insertCSS`)에는 페이지 정책이 적용되지 않는데, 이 부분은 검증하지 않았어요.
- 명령 샌드박스는 리소스와 프로세스를 제한하는 장치이지 **파일과 네트워크를 막는 벽이 아니에요**. 명령은 사용자 계정이 할 수 있는 모든 것을 읽고 쓸 수 있어요.
  진짜 격리(AppContainer, 별도 계정, 컨테이너)에는 관리자 권한이나 Docker가 필요해서 여기서는 만들지 않았어요.
- 모델은 틀리거나 속을 수 있어요. 그래서 보안은 모델의 "좋은 행동"이 아니라 확인 카드와 토큰에 기대요.
- `edge-tts` 음성 합성은 읽을 텍스트를 Microsoft 서비스로 보내요. 로컬 신경망을 쓸 때는 이것이 컴퓨터 밖으로 나가는 유일한 데이터예요.
  이것까지 집 안에 두려면 설정의 "음성"에서 "Windows 음성만"을 고르세요(`luna/senses/localtts.py`).
- Electron 셸과 트레이는 자동 테스트에서 검증하지 않아요.

취약점 신고: 프로젝트 소유자에게 직접 연락해 주세요(수정되기 전에는 세부 내용을 공개하지 마세요).
