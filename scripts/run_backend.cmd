@echo off
setlocal

echo ========================================================
echo  Starting FireScope Backend Server
echo ========================================================

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found.
    echo Please run scripts\setup_backend.cmd first.
    exit /b 1
)

set "PYTHONUNBUFFERED=1"

echo [INFO] Launching FastAPI via Uvicorn on http://127.0.0.1:8000
echo [INFO] Interactive OpenAPI documentation available at http://127.0.0.1:8000/docs
echo [INFO] Press Ctrl+C to terminate the server.
echo.

.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
exit /b %errorlevel%
