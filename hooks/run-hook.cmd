@echo off
REM Cross-platform hook runner for litestar-skills (Windows dispatch).
REM Dispatch order: PowerShell 7+ -> Windows PowerShell 5.1 -> Git Bash -> WSL.
REM
REM Usage: run-hook.cmd <hook-name>
REM   <hook-name> = session-start (the only hook today)

setlocal enableextensions

set "SCRIPT_DIR=%~dp0"
set "HOOK_NAME=%~1"

if "%HOOK_NAME%"=="" (
    echo {"error": "No hook name provided"} >&2
    exit /b 1
)

set "PS1_SCRIPT=%SCRIPT_DIR%%HOOK_NAME%.ps1"
set "SH_SCRIPT=%SCRIPT_DIR%%HOOK_NAME%.sh"

REM 1. Try PowerShell 7+ (pwsh) first
where pwsh.exe >nul 2>&1
if %ERRORLEVEL%==0 if exist "%PS1_SCRIPT%" (
    pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_SCRIPT%"
    exit /b %ERRORLEVEL%
)

REM 2. Fall back to Windows PowerShell 5.1
where powershell.exe >nul 2>&1
if %ERRORLEVEL%==0 if exist "%PS1_SCRIPT%" (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_SCRIPT%"
    exit /b %ERRORLEVEL%
)

REM 3. Fall back to Git Bash (Git for Windows)
set "BASH_EXE="
if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles%\Git\bin\bash.exe"
if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles(x86)%\Git\bin\bash.exe"
where bash.exe >nul 2>&1 && if not defined BASH_EXE for /f "delims=" %%i in ('where bash.exe') do set "BASH_EXE=%%i"

if defined BASH_EXE if exist "%SH_SCRIPT%" (
    "%BASH_EXE%" "%SH_SCRIPT%"
    exit /b %ERRORLEVEL%
)

echo {"error": "No supported runtime found. Install PowerShell 7+ (https://aka.ms/PSWindows) or Git for Windows (https://git-scm.com/download/win)."} >&2
exit /b 1
