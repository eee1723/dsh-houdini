@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\uninstall.ps1" %*
if errorlevel 1 (
  echo Uninstall did not complete. The message above explains what to check.
  pause
  exit /b 1
)
pause
