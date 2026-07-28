@echo off
chcp 65001 >nul 2>&1
title Hermes - Telegram Bot + Worker

echo ========================================
echo    HERMES - Telegram Bot + Worker
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.12+
    pause
    exit /b 1
)

:: Check .env
if not exist .env (
    echo [WARNING] .env file not found. Copying from .env.example...
    if exist .env.example (
        copy .env.example .env >nul 2>&1
    ) else (
        echo [ERROR] No .env or .env.example found
        pause
        exit /b 1
    )
)

:: Install requirements if needed
if not exist venv (
    echo [INFO] Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo.
echo [1/2] Starting Telegram Bot...
echo [2/2] Starting Worker...
echo.

:: Start worker in background
start "Hermes Worker" /min python -m workers.job_worker

:: Start telegram bot in foreground
python telegram_bot.py

echo.
echo [INFO] Bot stopped. Stopping worker...
taskkill /FI "WINDOWTITLE eq Hermes Worker" /F >nul 2>&1
echo Done.
