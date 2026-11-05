@echo off
REM One-time setup for The Muser Studio on Windows. Flags: -Gpu -Voice -Separate -Denoise -Extras -SkipCore
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1" %*
pause
