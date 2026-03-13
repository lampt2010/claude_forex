@echo off
title Forex Trading Bot - Background

set "BOT_DIR=%~dp0"
set "MT5_EXE=C:\Program Files\MetaTrader 5\terminal64.exe"
set "LOG_FILE=%BOT_DIR%logs\realtime_stdout.log"

if not exist "%BOT_DIR%logs" mkdir "%BOT_DIR%logs"

echo.
echo ============================================================
echo   FOREX TRADING BOT - CHAY BACKGROUND
echo ============================================================
echo.

:: 1. Kiem tra va khoi dong MT5
tasklist /fi "imagename eq terminal64.exe" 2>nul | find /i "terminal64.exe" >nul
if %errorlevel% neq 0 (
    echo [1/3] Khoi dong MetaTrader 5...
    start "" "%MT5_EXE%"
    timeout /t 20 /nobreak >nul
) else (
    echo [1/3] MetaTrader 5 dang chay - OK
)

:: 2. Kiem tra dependencies
echo [2/3] Kiem tra dependencies...
call "%BOT_DIR%venv\Scripts\activate.bat"
python -c "import crewai, MetaTrader5, structlog" >nul 2>&1
if %errorlevel% neq 0 (
    echo     Cai dat dependencies...
    pip install -r "%BOT_DIR%requirements.txt" --quiet
)
echo     Dependencies OK

:: 3. Dung bot cu neu dang chay
echo [3/3] Khoi dong Bot background...
taskkill /fi "windowtitle eq ForexBot_Worker" /f >nul 2>&1
timeout /t 1 /nobreak >nul

:: Khoi dong qua helper script
start "ForexBot_Worker" /min "%BOT_DIR%_run_bot.bat"

timeout /t 4 /nobreak >nul

:: Kiem tra ket qua
tasklist /fi "imagename eq python.exe" 2>nul | find "python.exe" >nul
if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo   BOT DA KHOI DONG THANH CONG
    echo.
    echo   Log : %LOG_FILE%
    echo   Stop: stop.bat
    echo ============================================================
) else (
    echo.
    echo   [LOI] Bot khong khoi dong duoc.
    echo   Kiem tra log: %LOG_FILE%
)
echo.
pause
