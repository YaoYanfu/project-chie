@echo off
chcp 65001 >nul
setlocal
title Project Chie
cd /d "%~dp0"
set "MAIBOT_PROJECT_ROOT=%CD%"

echo [Project Chie] 项目目录: %CD%
echo [Project Chie] 提示：通过 QQ 聊天前，请确保 NapCat 正在运行。
echo [Project Chie] 按 Ctrl+C 或关闭窗口可停止 Project Chie。
echo.

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [Project Chie] 未找到 %PYTHON_EXE%
    echo [Project Chie] 请先安装项目依赖。
    pause
    exit /b 1
)

"%PYTHON_EXE%" bot.py
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo [Project Chie] Project Chie 已停止。
pause
exit /b %EXIT_CODE%
