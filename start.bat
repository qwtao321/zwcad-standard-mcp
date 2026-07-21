@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run install.bat first.
  exit /b 1
)
.venv\Scripts\python.exe -m zwcad_standard_mcp.server
endlocal
