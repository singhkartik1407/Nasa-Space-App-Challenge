@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo  FireScope Backend Setup
echo ========================================================

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found.
    echo Please create the virtual environment using Python 3.11-3.13:
    echo   python -m venv .venv
    exit /b 1
)

echo [INFO] Installing required dependencies...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    exit /b %errorlevel%
)

echo [INFO] Setting up local package discovery...
echo %CD% > .venv\Lib\site-packages\firescope.pth

echo [INFO] Checking data file readiness...
.venv\Scripts\python.exe -c "from backend.services.duckdb_service import duckdb_service; r = duckdb_service.check_readiness(); print('Readiness:', r)"
if %errorlevel% neq 0 (
    echo [ERROR] Readiness check failed.
    exit /b %errorlevel%
)

echo.
echo [SUCCESS] FireScope backend setup completed successfully!
echo You can now run the backend using scripts\run_backend.cmd
exit /b 0
