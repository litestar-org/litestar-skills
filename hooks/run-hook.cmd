@echo off
REM Cross-platform hook runner for litestar-skills plugin (Windows dispatch).
REM Delegates to Git Bash to run the hook, since hooks are bash scripts.
REM
REM Usage: run-hook.cmd <hook-name>

setlocal enableextensions

set "SCRIPT_DIR=%~dp0"
set "HOOK_NAME=%~1"

if "%HOOK_NAME%"=="" (
    echo {"error": "No hook name provided"} >&2
    exit /b 1
)

set "HOOK_SCRIPT=%SCRIPT_DIR%%HOOK_NAME%"

if not exist "%HOOK_SCRIPT%" (
    echo {"error": "Hook script not found: %HOOK_NAME%"} >&2
    exit /b 1
)

REM Detect Git Bash (Git for Windows) - common install paths
set "BASH_EXE="
if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles%\Git\bin\bash.exe"
if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles(x86)%\Git\bin\bash.exe"
where bash.exe >nul 2>&1 && if not defined BASH_EXE for /f "delims=" %%i in ('where bash.exe') do set "BASH_EXE=%%i"

if not defined BASH_EXE (
    echo {"error": "Git Bash not found. Install Git for Windows from https://git-scm.com/download/win or use WSL."} >&2
    exit /b 1
)

"%BASH_EXE%" "%HOOK_SCRIPT%"
exit /b %ERRORLEVEL%
