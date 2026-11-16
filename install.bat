@echo off
rem Installs everything Luna needs on a new computer. Safe to run again: what is installed is left alone.
rem The real work is in tools\install.py (messages in English, Russian, Korean, Japanese: it follows the Windows language).
rem This file only makes sure Python exists. It never installs Ollama: whoever wants a local AI installs it themselves.
rem   install.bat                 install everything
rem   install.bat --check         only look, change nothing
rem   install.bat --lang ru       force a language: en, ru, ko, ja
chcp 65001 >nul
cd /d "%~dp0"

rem ---- the language: --lang xx, else the Windows display language, else English ----
set "L="
for %%a in (%*) do (
  if defined NEXT set "L=%%a" & set "NEXT="
  if /i "%%a"=="--lang" set "NEXT=1"
)
if not defined L for /f "delims=" %%i in ('powershell -NoProfile -Command "(Get-UICulture).TwoLetterISOLanguageName" 2^>nul') do set "L=%%i"
if /i not "%L%"=="ru" if /i not "%L%"=="ko" if /i not "%L%"=="ja" set "L=en"
set "NEXT="

set "PYCMD="
py -3 -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD python -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PYCMD=python"
if defined PYCMD goto run

call :say nopy
if /i "%~1"=="--check" goto nopython
where winget >nul 2>nul
if errorlevel 1 goto nowinget
call :say winget
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYCMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PYCMD goto run
call :say reopen
goto end

:nowinget
call :say nowinget
start "" https://www.python.org/downloads/
goto end

:nopython
call :say checkonly
goto end

:run
%PYCMD% "%~dp0tools\install.py" --lang %L% %*
:end
echo.
pause
goto :eof

rem ---- messages: :say <key> prints it in the chosen language ----
:say
goto say_%L%

:say_en
if "%1"=="nopy" echo Python 3.10 or newer was not found.
if "%1"=="winget" echo Installing Python 3.12 with winget. Windows may ask for permission: press Yes.
if "%1"=="reopen" echo Python was installed, but this window does not see it yet. Close this window and run install.bat again.
if "%1"=="nowinget" echo Automatic install is not available (no winget). Download Python from https://www.python.org/downloads/ , tick "Add python.exe to PATH" in the installer, then run install.bat again.
if "%1"=="checkonly" echo (check only: nothing is installed)
goto :eof

:say_ru
if "%1"=="nopy" echo Python 3.10 или новее не найден.
if "%1"=="winget" echo Устанавливаю Python 3.12 через winget. Windows может спросить разрешение: нажми «Да».
if "%1"=="reopen" echo Python установлен, но это окно его ещё не видит. Закрой окно и запусти install.bat ещё раз.
if "%1"=="nowinget" echo Автоустановка недоступна (нет winget). Скачай Python с https://www.python.org/downloads/ , в установщике поставь галку «Add python.exe to PATH», потом запусти install.bat ещё раз.
if "%1"=="checkonly" echo (только проверка: ничего не устанавливается)
goto :eof

:say_ko
if "%1"=="nopy" echo Python 3.10 이상을 찾을 수 없어요.
if "%1"=="winget" echo winget으로 Python 3.12를 설치합니다. Windows가 허용 여부를 물으면 "예"를 눌러 주세요.
if "%1"=="reopen" echo Python이 설치됐지만 이 창은 아직 인식하지 못해요. 창을 닫고 install.bat을 다시 실행해 주세요.
if "%1"=="nowinget" echo 자동 설치를 쓸 수 없어요 (winget 없음). https://www.python.org/downloads/ 에서 Python을 받아 설치 때 "Add python.exe to PATH"를 체크한 뒤 install.bat을 다시 실행해 주세요.
if "%1"=="checkonly" echo (확인만 합니다: 아무것도 설치하지 않아요)
goto :eof

:say_ja
if "%1"=="nopy" echo Python 3.10 以上が見つかりません。
if "%1"=="winget" echo winget で Python 3.12 をインストールします。Windows が許可を求めたら「はい」を押してください。
if "%1"=="reopen" echo Python をインストールしましたが、このウィンドウはまだ認識していません。閉じてから install.bat をもう一度実行してください。
if "%1"=="nowinget" echo 自動インストールは使えません（winget がありません）。https://www.python.org/downloads/ から Python を入手し、インストーラーで「Add python.exe to PATH」にチェックを入れてから install.bat をもう一度実行してください。
if "%1"=="checkonly" echo （確認のみ: 何もインストールしません）
goto :eof
