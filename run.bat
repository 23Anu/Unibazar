@echo off
setlocal
cd /d "%~dp0"
set "HOST=127.0.0.1"
set "PORT=5001"
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist ".venv\Scripts\python.exe" if exist "%LocalAppData%\Python\bin\python.exe" set "PYTHON=%LocalAppData%\Python\bin\python.exe"
"%PYTHON%" -c "import flask, dotenv" >nul 2>&1
if errorlevel 1 goto install_deps
goto launch
:install_deps
if not exist .venv (
  "%PYTHON%" -m venv .venv
  if errorlevel 1 goto failed
)
set "PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto failed
:launch
if not exist .env copy .env.example .env >nul
"%PYTHON%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/api/health',timeout=1)" >nul 2>&1
if errorlevel 1 start "UniBazar local server" "%PYTHON%" -u app.py
for /l %%i in (1,1,12) do (
  "%PYTHON%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/api/health',timeout=1)" >nul 2>&1
  if not errorlevel 1 goto ready
  "%PYTHON%" -c "import time; time.sleep(1)" >nul 2>&1
)
echo The local server did not respond on port 5001.
echo If Windows Firewall asks, allow Python on Private networks.
echo See the server window for the startup error.
pause
exit /b 1
:ready
start "" "http://127.0.0.1:5001/"
exit /b 0
:failed
echo Setup failed. Check Python installation and internet access, then try again.
pause
exit /b 1
