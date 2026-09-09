@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1" %*
if errorlevel 1 (
  echo Installation did not complete. The message above explains what to check.
  pause
  exit /b 1
)
echo DSH-Houdini is ready to manage from Houdini. Restart Houdini to load the menu.
pause
