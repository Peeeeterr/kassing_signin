@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

:: ==============================================================================
:: 学搭子自动化打卡助手统一交互控制台与启动批处理 (run.bat)
:: ==============================================================================

:: 1. 检测 Python 解释器路径 (优先读取 .env)
set "PYTHON_BIN=python"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="PYTHON_BIN" (
            if not "%%~B"=="" set "PYTHON_BIN=%%~B"
        )
    )
)
if "%PYTHON_BIN%"=="python" (
    if exist ".venv\Scripts\python.exe" (
        set "PYTHON_BIN=.venv\Scripts\python.exe"
    ) else if exist "venv\Scripts\python.exe" (
        set "PYTHON_BIN=venv\Scripts\python.exe"
    )
)

:: 2. 检查核心依赖库并自动修复
"%PYTHON_BIN%" -c "import requests, PIL" 2>nul
if %ERRORLEVEL% neq 0 (
    echo ====================================================================
    echo [*] 正在检查并自动安装 Python 依赖库 (requirements.txt)...
    echo ====================================================================
    "%PYTHON_BIN%" -m pip install -r requirements.txt
    if %ERRORLEVEL% equ 0 (
        echo [+] 依赖环境准备完毕！
    ) else (
        echo [-] 依赖安装失败，请检查网络连接。
    )
)

:: 3. 若带有命令行参数，直接透明透传执行
if not "%1"=="" (
    "%PYTHON_BIN%" main.py %*
    exit /b %ERRORLEVEL%
)

:: 4. 检测是否已完成环境配置，未完成则拉起向导
if not exist ".env" (
    echo ====================================================================
    echo [*] 检测到项目尚未初始化配置，正在为您启动配置向导...
    echo ====================================================================
    "%PYTHON_BIN%" main.py -init
    echo.
    echo 向导执行完毕，按任意键进入控制台管理面板...
    pause >nul
)

:: 5. 交互式控制台菜单循环
:menu_loop
cls
echo ====================================================================
echo             学搭子 (kassing-signin) 控制台管理面板                  
echo ====================================================================

set HAS_SCHED=0
schtasks /query /fo list 2>nul | findstr /i "Kassing_" >nul 2>&1
if %ERRORLEVEL% equ 0 set HAS_SCHED=1

if "%HAS_SCHED%"=="0" (
    echo   [当前状态] 尚未配置自动打卡
    echo              提示: 可输入 [6] 一键开启每天定时打卡
) else if exist ".pause" (
    echo   [当前状态] 自动打卡已开启 · 当前状态: 暂停打卡
    echo              提示: 到点将自动跳过，恢复打卡请按 [5]
) else if exist ".skip" (
    echo   [当前状态] 自动打卡已开启 · 当前状态: 跳过打卡生效中
    echo              提示: 下次打卡将自动跳过并递减，取消/恢复请按 [5]
) else (
    echo   [当前状态] 自动打卡已开启 · 当前状态: 正常运行中
    echo              提示: 到点将自动打卡，放假调休暂停请按 [4]
)
echo --------------------------------------------------------------------
echo   【打卡服务】
echo     [1] 立即签到
echo     [2] 常规签到
echo     [3] 查看今日签到记录与状态
echo.
echo   【自动打卡与假期管理】
echo     [4] 暂停自动打卡
echo     [5] 恢复自动打卡
echo     [6] 开启 / 修改自动打卡时间
echo     [7] 关闭 / 卸载自动打卡任务
echo     [8] 查看自动打卡状态与运行日志
echo     [9] 跳过下次打卡
echo.
echo   【测试与演练工具】
echo    [10] 演练打卡全流程
echo    [11] 测试本地水印合成
echo    [12] 诊断账号状态与底图池健康度
echo    [13] 测试系统定时器与调度健康度
echo.
echo   【设置与维护】
echo    [14] 重新运行配置向导
echo    [15] 检查并修复运行环境
echo.
echo     [0] 退出控制台
echo ====================================================================
set /p choice=请输入选项编号 [0-15]: 

if "%choice%"=="1" cls & "%PYTHON_BIN%" main.py -y & goto end_action
if "%choice%"=="2" cls & "%PYTHON_BIN%" main.py & goto end_action
if "%choice%"=="3" cls & "%PYTHON_BIN%" main.py -records & goto end_action
if "%choice%"=="4" cls & "%PYTHON_BIN%" main.py -pause & goto end_action
if "%choice%"=="5" cls & "%PYTHON_BIN%" main.py -resume & goto end_action
if "%choice%"=="6" cls & "%PYTHON_BIN%" main.py -setup-cron & goto end_action
if "%choice%"=="7" cls & "%PYTHON_BIN%" main.py -remove-cron & goto end_action
if "%choice%"=="8" cls & "%PYTHON_BIN%" main.py -status & goto end_action
if "%choice%"=="9" cls & "%PYTHON_BIN%" main.py --skip-interactive & goto end_action
if "%choice%"=="10" cls & "%PYTHON_BIN%" main.py --dry-run & goto end_action
if "%choice%"=="11" cls & "%PYTHON_BIN%" scripts\test_watermark.py & goto end_action
if "%choice%"=="12" cls & "%PYTHON_BIN%" scripts\check_status.py & goto end_action
if "%choice%"=="13" cls & "%PYTHON_BIN%" scripts\test_timer.py & goto end_action
if "%choice%"=="14" cls & "%PYTHON_BIN%" main.py -init & goto end_action
if "%choice%"=="15" cls & "%PYTHON_BIN%" -m pip install -r requirements.txt & goto end_action
if "%choice%"=="0" exit /b 0
if /i "%choice%"=="q" exit /b 0

echo.
echo [提示] 输入无效，请输入 0 到 15 之间的数字。

:end_action
echo.
echo --------------------------------------------------------------------
echo 按任意键返回主菜单...
pause >nul
goto menu_loop
