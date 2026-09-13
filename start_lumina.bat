@echo off
title Lumina Studio - Bulb Bridge
echo ===================================================
echo   Lumina Studio - Cloud Bridge for Tasmota Bulb
echo ===================================================
echo.
echo [1/2] Starting Python Local Bridge on port 7070...
start /b python server.py
timeout /t 2 >nul

echo [2/2] Connecting ngrok Cloud Tunnel...
ngrok http 7070 --url https://epidermis-coliseum-masses.ngrok-free.dev
pause
