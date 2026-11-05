@echo off
REM Launch The Muser Studio. Options: -Demo  -Port 8765  -Gradio  -NoBrowser
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_studio.ps1" %*
pause
