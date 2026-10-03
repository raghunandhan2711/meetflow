@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.ps1 first. See README.md for setup instructions.
  pause
  exit /b 1
)
if not exist ".env" copy ".env.example" ".env" >nul
echo Meeting Analysis is available at http://127.0.0.1:8000
echo Press Ctrl+C to stop the server.
".venv\Scripts\python.exe" run.py
