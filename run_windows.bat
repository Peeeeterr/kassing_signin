@echo off
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

:: ==============================================================================
:: 学搭子定时打卡任务运行脚本 (Windows 计划任务执行端 run_windows.bat)
:: ==============================================================================

if not exist "logs" mkdir logs
set "LOG_FILE=logs\cron.log"

:: 检查是否存在调休/节假日暂停标识文件 (.pause)
if exist ".pause" (
    echo [%date% %time%] [Task] Found .pause flag, skipping scheduled signin task. >> "%LOG_FILE%"
    exit /b 0
)

set "EXTRA_ARGS="
set "DO_WAIT=1"
set "MAX_DELAY=180"

:parse_loop
if "%~1"=="" goto end_parse_loop
if /i "%~1"=="--immediate" (
    set "DO_WAIT=0"
    shift
    goto parse_loop
)
echo %~1| findstr /r "^[0-9][0-9]*$" >nul 2>&1
if not errorlevel 1 (
    if "%DO_WAIT%"=="1" (
        set "MAX_DELAY=%~1"
        shift
        goto parse_loop
    )
)
set "EXTRA_ARGS=%EXTRA_ARGS% %1"
shift
goto parse_loop
:end_parse_loop

if "%DO_WAIT%"=="0" (
    set "RANDOM_DELAY=0"
) else (
    set /a "MIN_DELAY=10"
    if %MAX_DELAY% leq 10 (
        set "RANDOM_DELAY=%MAX_DELAY%"
    ) else (
        set /a "SPAN=%MAX_DELAY% - 10"
        set /a "RANDOM_DELAY=10 + (%RANDOM% %% SPAN)"
    )
    echo [%date% %time%] [Task] Scheduled trigger [max delay: %MAX_DELAY%s], random wait: %RANDOM_DELAY%s >> "%LOG_FILE%"
    timeout /t %RANDOM_DELAY% /nobreak >nul 2>&1
)

:: 探测 Python 解释器
set "PYTHON_EXE="
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"

if not defined PYTHON_EXE (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
    where py >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=py"
)

if not defined PYTHON_EXE (
    echo [%date% %time%] [Task Error] Python interpreter not found! >> "%LOG_FILE%"
    exit /b 1
)

echo ======================================================== >> "%LOG_FILE%"
echo [%date% %time%] [Task] Starting automated sign-in task... >> "%LOG_FILE%"
echo [%date% %time%] [Task] Interpreter: %PYTHON_EXE% >> "%LOG_FILE%"

"%PYTHON_EXE%" "%~dp0main.py" -y %EXTRA_ARGS% >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

echo [%date% %time%] [Task] Task execution finished, exit code: %EXIT_CODE% >> "%LOG_FILE%"
echo ======================================================== >> "%LOG_FILE%"

exit /b %EXIT_CODE%
