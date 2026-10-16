@echo off
setlocal EnableExtensions

REM ===========================================================================
REM  Adobe Stock AI Image Studio - development launcher
REM
REM  Opens two separate CMD windows:
REM    * Backend  - FastAPI / uvicorn on http://localhost:8007
REM    * Frontend - Next.js dev server on http://localhost:3100 (frontend-new)
REM
REM  Usage: double-click this file, or run "start-dev.cmd" from any terminal.
REM
REM  Each window re-invokes this same file with a label argument
REM  (":run_backend" / ":run_frontend") so the child processes inherit the
REM  environment configured below. Editing the port block is all that is needed
REM  to move the app to different ports.
REM ===========================================================================

REM --- Paths ----------------------------------------------------------------
set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "BACKEND_DIR=%REPO_ROOT%\backend"
set "FRONTEND_DIR=%REPO_ROOT%\frontend-new"
set "VENV_PY=%BACKEND_DIR%\.venv\Scripts\python.exe"

REM --- Ports ----------------------------------------------------------------
set "BACKEND_PORT=8007"
set "FRONTEND_PORT=3100"

REM --- Re-entrant entry points for the child windows ------------------------
if /i "%~1"==":run_backend"  goto run_backend
if /i "%~1"==":run_frontend" goto run_frontend

REM --- Pre-flight checks ----------------------------------------------------
if not exist "%VENV_PY%" (
    echo [ERROR] Backend virtual environment not found:
    echo         %VENV_PY%
    echo.
    echo         Create it once with:
    echo             cd /d "%BACKEND_DIR%"
    echo             python -m venv .venv
    echo             .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm was not found on PATH. Install Node.js first.
    echo.
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo [WARN] frontend\node_modules is missing - the frontend window may fail.
    echo        Run "npm install" in %FRONTEND_DIR% if it does.
    echo.
)

REM --- Launch both windows --------------------------------------------------
echo Starting Adobe Stock AI Image Studio...
echo   Backend  : http://localhost:%BACKEND_PORT%   -  API docs at /docs
echo   Frontend : http://localhost:%FRONTEND_PORT%
echo.
echo Opening the backend window now, then the frontend window in 3 seconds.
echo.

start "Backend - uvicorn on %BACKEND_PORT%" cmd /k ""%~f0" :run_backend"

REM Give the API a head start so the first page load does not hit a dead port.
timeout /t 3 /nobreak >nul

start "Frontend - next dev on %FRONTEND_PORT%" cmd /k ""%~f0" :run_frontend"

echo Both CMD windows have been opened. This launcher window can be closed.
exit /b 0


REM ===========================================================================
REM  Backend window - FastAPI application served by uvicorn
REM ===========================================================================
:run_backend
title Backend - uvicorn on %BACKEND_PORT%
cd /d "%BACKEND_DIR%"

REM BACKEND_PORT is already exported by the launcher, so config.py and the
REM actual uvicorn listener agree on the same port.

REM CORS_ORIGINS is a list field in config.py, so pydantic-settings parses it as
REM JSON. Without this the browser blocks the frontend's cross-port API calls,
REM because the default list only allows port 3100.
set "CORS_ORIGINS=["http://localhost:%FRONTEND_PORT%","http://127.0.0.1:%FRONTEND_PORT%"]"

REM Listen on all interfaces so the mobile app can reach the backend over
REM the LAN via the PC's IPv4 address (the Local profile's physical-device
REM path); localhost keeps working and the tunnel is unaffected.
echo Starting backend on http://localhost:%BACKEND_PORT% (LAN: 0.0.0.0) ...
echo.
"%VENV_PY%" -m uvicorn main:app --reload --port %BACKEND_PORT% --host 0.0.0.0

echo.
echo Backend process exited.
pause
goto :eof


REM ===========================================================================
REM  Frontend window - Next.js development server
REM ===========================================================================
:run_frontend
title Frontend - next dev on %FRONTEND_PORT%
cd /d "%FRONTEND_DIR%"

REM PORT is set here and passed again via --port so the dev server port is
REM unambiguous regardless of what .env.local contains.
set "PORT=%FRONTEND_PORT%"
set "NEXT_PUBLIC_API_BASE_URL=http://localhost:%BACKEND_PORT%"

echo Starting frontend on http://localhost:%FRONTEND_PORT% ...
echo.
call npm run dev -- --port %FRONTEND_PORT%

echo.
echo Frontend process exited.
pause
goto :eof
