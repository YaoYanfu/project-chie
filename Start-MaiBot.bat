@echo off
setlocal

title MaiBot
cd /d "C:\Users\Legiony\Documents\GitHub\MaiBot"
set "MAIBOT_PROJECT_ROOT=C:\Users\Legiony\Documents\GitHub\MaiBot"

echo [MaiBot] Project: %cd%
echo [MaiBot] Tip: keep NapCat running before chatting on QQ.
echo [MaiBot] Press Ctrl+C or close this window to stop MaiBot.
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" bot.py
) else (
    echo [MaiBot] Cannot find .venv\Scripts\python.exe
    echo [MaiBot] Please install project dependencies first.
    echo.
    pause
    exit /b 1
)

echo.
echo [MaiBot] MaiBot has stopped.
pause
