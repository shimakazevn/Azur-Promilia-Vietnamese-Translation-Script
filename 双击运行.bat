@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "HINT=%~1"
if defined HINT set "HINT=%HINT:"=%"
if not defined HINT (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Manage-Localization.ps1"
) else (
  if not "%HINT:~1%"==":\" if "%HINT:~-1%"=="\" set "HINT=%HINT:~0,-1%"
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Manage-Localization.ps1" -Hint "%HINT%"
)
set "RESULT=%ERRORLEVEL%"
echo.
echo 按任意键继续……
pause >nul
exit /b %RESULT%
