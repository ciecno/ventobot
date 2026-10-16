@echo off
title Fortnite Discord Bot
echo ========================================================
echo       Starting Fortnite Discord Bot...
echo ========================================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to PATH.
    pause
    exit /b
)

echo Starting bot...
echo.
python bot.py

echo.
echo Bot stopped.
pause
