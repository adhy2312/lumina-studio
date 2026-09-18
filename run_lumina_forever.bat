@echo off
title Lumina Studio 24/7 Watchdog
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0run_lumina_forever.ps1"
pause
