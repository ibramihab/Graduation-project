@echo off
REM Double-click this file to get the newest version of the project from GitHub.
REM Your .env settings and data\ folder (your devices) are NOT touched.
cd /d "%~dp0"

git pull
if errorlevel 1 (
    echo.
    echo git pull failed. Send a screenshot of this window.
    pause
    exit /b
)

if not exist venv\Scripts\python.exe python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt

echo.
echo Update finished. Now double-click start.bat
pause
