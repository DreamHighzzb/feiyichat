@echo off
cd /d "%~dp0"
set "PY=C:\Users\95477\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"
for /f %%a in ('"%PY%" -c "import json;print(json.load(open('config.json',encoding='utf-8')).get('server',{}).get('port',5222))"') do set "PORT=%%a"
if not defined PORT set "PORT=5222"

echo [1/2] Checking port %PORT%...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo Killing PID %%P ...
    taskkill /PID %%P /F >nul 2>nul
)

echo [2/2] Starting FeiYi QQ...
echo ----------------------------------------
"%PY%" "feiyichat_app.py"

echo.
echo Server exited.
pause
