@echo off
powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0installer\open-workbench.ps1" -SourceRoot "%~dp0."
