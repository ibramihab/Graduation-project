@echo off
REM Double-click this file to get the newest version of the project from GitHub.
REM Your .env settings and data\ folder (your devices) are NOT touched.

REM Windows reads a .bat file line by line WHILE it runs. "git pull" may replace this
REM file, so we first copy it to a temporary file and run that copy instead.
if not "%~1"=="--copy" (
    copy /y "%~f0" "%TEMP%\ibn_update.bat" >nul
    "%TEMP%\ibn_update.bat" --copy "%~dp0."
)
cd /d "%~2"

for /f %%i in ('git rev-parse HEAD') do set BEFORE=%%i
git pull -q
if errorlevel 1 (
    echo.
    echo git pull failed. Send a screenshot of this window.
    pause
    exit /b
)
for /f %%i in ('git rev-parse HEAD') do set AFTER=%%i

if "%BEFORE%"=="%AFTER%" (
    echo No new changes. You already have the newest version.
) else (
    echo New changes downloaded:
    git --no-pager log --format="  - %%s" %BEFORE%..%AFTER%
)

REM Install libraries only if they are missing or requirements.txt changed (quietly)
if not exist venv\Scripts\python.exe (
    echo.
    echo Installing libraries, please wait...
    python -m venv venv
    venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt
) else (
    git diff --quiet %BEFORE% %AFTER% -- requirements.txt
    if errorlevel 1 (
        echo.
        echo The list of libraries changed: updating them, please wait...
        venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt
    )
)

echo.
echo Update finished. Now double-click start.bat
pause
