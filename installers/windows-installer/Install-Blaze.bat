@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Blaze.ps1"
set "BLAZE_RESULT=%ERRORLEVEL%"
echo.
if not "%BLAZE_RESULT%"=="0" echo Installation failed. Read the error above, then rerun this installer.
pause
exit /b %BLAZE_RESULT%

