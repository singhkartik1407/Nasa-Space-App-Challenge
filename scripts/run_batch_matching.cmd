@echo off
setlocal
cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [FireScope] Executing batch matching runner with args: %*
"%PYTHON_EXE%" scripts\batch_match_historical.py %*
exit /b %ERRORLEVEL%
