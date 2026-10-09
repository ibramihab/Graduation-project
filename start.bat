@echo off
REM Double-click this file to start the IBN program.
cd /d "%~dp0"

REM First time only: create the virtual environment and install libraries
if not exist venv\Scripts\python.exe (
    echo First run: installing libraries, please wait...
    python -m venv venv
    venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt
)

REM First time only: create the settings file
if not exist .env (
    copy .env.example .env >nul
    echo.
    echo Created the settings file ".env". Open it in Notepad, check it, then run start.bat again.
    notepad .env
    pause
    exit /b
)

echo Starting... open http://localhost:5000 in your browser. Close this window to stop.
venv\Scripts\python.exe run.py
pause
