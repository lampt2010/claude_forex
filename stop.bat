@echo off
title Forex Trading Bot - Stop

echo.
echo ============================================================
echo   DUNG FOREX TRADING BOT
echo ============================================================
echo.

tasklist /fi "imagename eq python.exe" 2>nul | find "python.exe" >nul
if %errorlevel% equ 0 (
    echo Dang dung bot...
    taskkill /im python.exe /f >nul 2>&1
    echo Bot da dung.
) else (
    echo Khong tim thay bot dang chay.
)

echo.
pause >nul
