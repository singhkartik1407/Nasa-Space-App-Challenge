@echo off
setlocal

echo ========================================================
echo  FireScope Full-Stack Application Launcher
echo ========================================================
echo  Backend:  FastAPI + DuckDB (http://127.0.0.1:8000)
echo  Frontend: React + Vite     (http://127.0.0.1:5173)
echo ========================================================
echo.

set "SCRIPT_DIR=%~dp0"

echo [1/2] Spawning FireScope Backend in separate window...
start "FireScope Backend API" cmd /c call "%SCRIPT_DIR%run_backend.cmd"

echo [2/2] Spawning FireScope Frontend in separate window...
start "FireScope Web Client" cmd /c call "%SCRIPT_DIR%run_frontend.cmd"

echo.
echo Both services have been started in dedicated Windows CMD windows.
echo - Backend API:  http://127.0.0.1:8000/docs
echo - Frontend UI:  http://127.0.0.1:5173
echo.
exit /b 0
