@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m venv .venv
if errorlevel 1 py -3.10 -m venv .venv
if errorlevel 1 (
  echo [ERROR] Python 3.10+ is required.
  exit /b 1
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e .
if errorlevel 1 exit /b 1
echo.
echo Installation complete.
echo Start ZWCAD and open a DWG, then run start.bat.
endlocal
