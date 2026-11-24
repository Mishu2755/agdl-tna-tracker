@echo off
setlocal
title AGDL T&A Tracker
color 0B
cd /d "%~dp0"

echo ===============================================================================
echo                AGDL T^&A TRACKER - 1-CLICK LAUNCHER
echo                         Aman Knittings Ltd.
echo ===============================================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

echo [INFO] Starting AGDL T^&A Tracker Web Server on http://localhost:5000 ...
start "" "http://localhost:5000"
python app.py

pause
