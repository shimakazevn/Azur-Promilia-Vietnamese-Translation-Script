@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "HINT=%~1"
if not defined HINT goto AUTO
if "%HINT:~-1%"=="\" set "HINT=%HINT%."
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Manage-Localization.ps1" -Hint "%HINT%"
goto DONE
:AUTO
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Manage-Localization.ps1"
:DONE
set "RESULT=%ERRORLEVEL%"
echo.
echo 按任意键继续……
pause >nul
exit /b %RESULT%
