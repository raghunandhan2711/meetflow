@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.ps1 first. See README.md for setup instructions.
  pause
  exit /b 1
)
if not exist ".env" copy ".env.example" ".env" >nul
echo Starting MeetFlow...
".venv\Scripts\python.exe" run.py
if errorlevel 1 (
  echo The website could not start. Check the error above.
  pause
  exit /b 1
)
