@echo off
rem Installs everything Luna needs on a new computer. Safe to run again: what is installed is left alone.
rem The real work is in install.py (Russian text, easy to extend). This file only makes sure Python exists.
rem   install.bat            install everything
rem   install.bat --check    only look, change nothing
rem   install.bat --ollama   also install Ollama (local AI) without asking
cd /d "%~dp0"
set "PYCMD="
py -3 -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD python -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PYCMD=python"
if defined PYCMD goto run

echo Python 3.10 or newer was not found.
if /i "%~1"=="--check" goto nopython
where winget >nul 2>nul
if errorlevel 1 goto nowinget
echo Installing Python 3.12 with winget. Windows may ask for permission: press Yes.
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYCMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PYCMD goto run
echo Python was installed, but this window does not see it yet. Close this window and run install.bat again.
goto end

:nowinget
echo Automatic install is not available (no winget).
echo Download Python from https://www.python.org/downloads/ , tick "Add python.exe to PATH" in the installer, then run install.bat again.
start "" https://www.python.org/downloads/
goto end

:nopython
echo (check only: nothing is installed)
goto end

:run
%PYCMD% "%~dp0install.py" %*
:end
echo.
pause
