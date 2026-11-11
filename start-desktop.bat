@echo off
cd /d "%~dp0"
if not exist desktop\node_modules (
  echo First run: installing Electron...
  pushd desktop
  call npm install --no-audit --no-fund
  popd
)
pushd desktop
call npm start
popd
pause
