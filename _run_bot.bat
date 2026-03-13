@echo off
set BOT_DIR=%~dp0
call "%BOT_DIR%venv\Scripts\activate.bat"
cd /d "%BOT_DIR%"
python main.py > "%BOT_DIR%logs\realtime_stdout.log" 2>&1
