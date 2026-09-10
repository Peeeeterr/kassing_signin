@echo off
:: ==============================================================================
:: 学搭子定时打卡任务运行脚本 (Windows 批处理版本 run_windows.bat)
:: 专为 Windows 任务计划程序 (Task Scheduler) 设计：
:: 1. 自动定位当前目录
:: 2. 自动检测 .venv 虚拟环境或系统 Python
:: 3. 随机防风控延时 (默认 10~180 秒，支持传入参数例如 300)
:: 4. 输出追加记录到 logs\cron.log
:: ==============================================================================

chcp 65001 >nul
cd /d "%~dp0"

if not exist "logs" mkdir logs
set LOG_FILE=logs\cron.log

:: 检查是否存在调休/节假日暂停标识文件 (.pause)
if exist ".pause" (
    echo [%date% %time%] [Task] 检测到 .pause 暂停标识文件，跳过本次打卡任务。 >> %LOG_FILE%
    exit /b 0
)

set MAX_DELAY=%1
if "%MAX_DELAY%"=="" set MAX_DELAY=180

if "%MAX_DELAY%"=="--immediate" (
    set RANDOM_DELAY=0
) else (
    set /a MIN_DELAY=10
    set /a SPAN=%MAX_DELAY% - %MIN_DELAY%
    if %SPAN% leq 0 (
        set RANDOM_DELAY=%MAX_DELAY%
    ) else (
        set /a RANDOM_DELAY=%MIN_DELAY% + (%RANDOM% %% %SPAN%)
    )
    echo [%date% %time%] [Task] 触发定时打卡 (最大窗口: %MAX_DELAY%s)，随机等待: %RANDOM_DELAY% 秒... >> %LOG_FILE%
    timeout /t %RANDOM_DELAY% /nobreak >nul
)

:: 检测 Python 解释器路径 (优先读取 .env)
set PYTHON_BIN=python
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="PYTHON_BIN" (
            if not "%%~B"=="" set "PYTHON_BIN=%%~B"
        )
    )
)
if "%PYTHON_BIN%"=="python" (
    if exist ".venv\Scripts\python.exe" (
        set PYTHON_BIN=.venv\Scripts\python.exe
    ) else if exist "venv\Scripts\python.exe" (
        set PYTHON_BIN=venv\Scripts\python.exe
    )
)

echo ======================================================== >> %LOG_FILE%
echo [%date% %time%] 开始执行自动打卡任务... >> %LOG_FILE%

"%PYTHON_BIN%" main.py -y >> %LOG_FILE% 2>&1
set EXIT_CODE=%ERRORLEVEL%

echo [%date% %time%] 任务执行完毕，退出码: %EXIT_CODE% >> %LOG_FILE%
echo ======================================================== >> %LOG_FILE%

exit /b %EXIT_CODE%
