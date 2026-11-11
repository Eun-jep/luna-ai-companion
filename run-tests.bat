@echo off
cd /d "%~dp0"
py tests\run_all.py %*
pause
