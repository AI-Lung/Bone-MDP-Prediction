@echo off
setlocal

set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\bootstrap_windows.ps1"
if errorlevel 1 (
  echo.
  echo Launch failed. Please review the messages above.
  pause
)
