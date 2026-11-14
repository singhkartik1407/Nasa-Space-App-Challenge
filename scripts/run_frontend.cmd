@echo off
setlocal

echo ========================================================
echo  Starting FireScope Frontend (Vite + React)
echo ========================================================

cd /d "%~dp0\..\frontend"

if not exist "node_modules" (
    echo [ERROR] node_modules directory not found in frontend.
    echo Please run 'npm ci' inside frontend first.
    exit /b 1
)

echo [INFO] Starting Vite development server on http://127.0.0.1:5173
echo [INFO] Target Backend API: http://127.0.0.1:8000/api/v1
echo [INFO] Press Ctrl+C to terminate the frontend dev server.
echo.

call npm run dev -- --host 127.0.0.1 --port 5173
exit /b %errorlevel%
