@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1" %*
if errorlevel 1 (
  echo Installation did not complete. The message above explains what to check.
  pause
  exit /b 1
)
echo Houdini helpers are registered. Restart Houdini to load the menu.
echo Install and update the dsh-houdini plugin through official DSH Desktop.
pause
