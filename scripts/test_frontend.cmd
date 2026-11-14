@echo off
setlocal

echo ========================================================
echo  Running FireScope Frontend Verification
echo ========================================================

cd /d "%~dp0\..\frontend"

if not exist "node_modules" (
    echo [ERROR] node_modules not found. Running npm ci...
    call npm ci
)

echo [INFO] Running TypeScript type check (tsc -b)...
call npx tsc -b
if %errorlevel% neq 0 (
    echo [ERROR] TypeScript compilation failed!
    exit /b %errorlevel%
)

echo [INFO] Running Vite production build...
call npm run build
if %errorlevel% neq 0 (
    echo [ERROR] Frontend build failed!
    exit /b %errorlevel%
)

echo.
echo ========================================================
echo  [SUCCESS] FireScope Frontend Build and Checks Passed!
echo ========================================================
exit /b 0
