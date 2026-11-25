@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Manage-Localization.ps1"
) else (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Manage-Localization.ps1" -Hint "%~1"
)
set "RESULT=%ERRORLEVEL%"
echo.
echo 按任意键继续……
pause >nul
exit /b %RESULT%
