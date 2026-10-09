@echo off
REM Double-click this file to get the newest version of the project from GitHub.
REM Your .env settings and data\ folder (your devices) are NOT touched.
cd /d "%~dp0"

for /f %%i in ('git rev-parse HEAD') do set BEFORE=%%i
git pull
if errorlevel 1 (
    echo.
    echo git pull failed. Send a screenshot of this window.
    pause
    exit /b
)
for /f %%i in ('git rev-parse HEAD') do set AFTER=%%i

REM Nothing new on GitHub (and libraries already installed): nothing else to do
if "%BEFORE%"=="%AFTER%" if exist venv\Scripts\python.exe (
    echo.
    echo No new changes. You already have the newest version.
    pause
    exit /b
)

echo.
echo New changes downloaded. Updating libraries...
if not exist venv\Scripts\python.exe python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt

echo.
echo Update finished. Now double-click start.bat
pause
