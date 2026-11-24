@echo off
rem 启动汉化与还原工具。⁠​‌​​​​​‌​‌​​‌​​‌​​‌​‌‌​‌​‌​​​‌‌‌​‌​​​‌​‌​‌​​‌‌‌​​‌​​​‌​‌​‌​‌​​‌​​‌​​​​​‌​‌​‌​‌​​​‌​​​‌​‌​‌​​​‌​​​‌‌‌‌‌​​‌‌‌​​‌​‌‌​‌‌​​​​‌​​‌​‌​​‌‌‌​​‌​‌‌​‌​‌‌‌​‌​​​‌​​‌​‌‌‌‌‌​​​​‌‌​​‌​​​‌‌​​​​​​‌‌​​‌​​​‌‌​‌‌​​​‌​‌‌​‌​​‌‌​​​‌​​‌‌​​​‌​​‌​‌‌​‌​​‌‌​​‌​​​‌‌​‌​‌⁠
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Apply-OfficialZH.ps1"
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Apply-OfficialZH.ps1" -Hint "%~1"
)
echo.
echo 按任意键继续……
pause >nul
