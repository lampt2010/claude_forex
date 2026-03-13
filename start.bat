@echo off
title Forex Trading Bot

set "BOT_DIR=%~dp0"
set "MT5_EXE=C:\Program Files\MetaTrader 5\terminal64.exe"

if not exist "%BOT_DIR%logs" mkdir "%BOT_DIR%logs"

echo.
echo ============================================================
echo   FOREX TRADING BOT - KHOI DONG
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

:: 3. Chay bot (hien log truc tiep)
echo [3/3] Khoi dong Bot...
echo.
echo   Log : %BOT_DIR%logs\realtime_stdout.log
echo   Dung: Ctrl+C hoac dong cua so nay
echo.
echo ============================================================
echo.

cd /d "%BOT_DIR%"
python main.py

echo.
echo Bot da dung. Nhan phim bat ky de thoat...
pause >nul
