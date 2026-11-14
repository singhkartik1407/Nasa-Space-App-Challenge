@echo off
setlocal

echo ========================================================
echo  Running FireScope Backend Test Suite
echo ========================================================

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found.
    echo Please run scripts\setup_backend.cmd first.
    exit /b 1
)

set "PYTHONUNBUFFERED=1"

echo [INFO] Executing Pytest test suite...
.venv\Scripts\python.exe -m pytest tests -v
if %errorlevel% neq 0 (
    echo [ERROR] Pytest suite failed with exit code %errorlevel%
    exit /b %errorlevel%
)

echo.
echo [INFO] Executing direct route verification script...
.venv\Scripts\python.exe -u scripts\test_direct_routes.py
if %errorlevel% neq 0 (
    echo [ERROR] Route verification script failed with exit code %errorlevel%
    exit /b %errorlevel%
)

echo.
echo ========================================================
echo  [SUCCESS] All FireScope Backend Tests Passed!
echo ========================================================
exit /b 0
