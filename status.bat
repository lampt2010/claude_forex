@echo off
title Forex Trading Bot - Status

set "LOG_FILE=%~dp0logs\realtime_stdout.log"

echo.
echo ============================================================
echo   FOREX TRADING BOT - TRANG THAI
echo ============================================================
echo.

:: Kiem tra MT5
tasklist /fi "imagename eq terminal64.exe" 2>nul | find /i "terminal64.exe" >nul
if %errorlevel% equ 0 (
    echo [MT5]  MetaTrader 5  : DANG CHAY
) else (
    echo [MT5]  MetaTrader 5  : KHONG CHAY
)

:: Kiem tra bot Python
tasklist /fi "imagename eq python.exe" 2>nul | find "python.exe" >nul
if %errorlevel% equ 0 (
    echo [BOT]  Trading Bot   : DANG CHAY
) else (
    echo [BOT]  Trading Bot   : KHONG CHAY
)

echo.
echo ---- LOG GAN NHAT -----------------------------------------
echo.
if exist "%LOG_FILE%" (
    powershell -command "Get-Content '%LOG_FILE%' -Tail 30 | Select-String 'source|decision|SELL|BUY|HOLD|Cycle|error|ERROR'"
) else (
    echo (Chua co log)
)

echo.
echo ============================================================
pause >nul
