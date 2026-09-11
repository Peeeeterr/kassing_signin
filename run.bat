@echo off
chcp 936 >nul 2>&1
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

:: ==============================================================================
:: 学搭子自动化打卡助手统一交互控制台与启动批处理 (run.bat)
:: ==============================================================================

:: 1. 检测 Python 解释器
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
    cls
    echo ====================================================================
    echo [错误] 未检测到 Python 运行环境！
    echo ====================================================================
    echo 请确认 Windows 上已安装 Python 3.9 或更高版本。
    echo 安装时请务必勾选：
    echo   [x] Add python.exe to PATH
    echo.
    echo 官方下载地址: https://www.python.org/downloads/
    echo 若刚刚完成安装，请尝试重启电脑或重新打开命令行。
    echo ====================================================================
    echo.
    pause
    exit /b 1
)

:: 2. 检查核心依赖库并自动修复
"%PYTHON_EXE%" -c "import requests, PIL" >nul 2>&1
if not errorlevel 1 goto :deps_ok

echo ====================================================================
echo [*] 正在检查并自动安装 Python 依赖库 [requirements.txt] ...
echo ====================================================================
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [-] 依赖安装失败，请检查网络连接。
    pause
) else (
    echo [+] 依赖环境准备完毕！
)

:deps_ok

:: 3. 命令行参数透传执行
if not "%~1"=="" (
    "%PYTHON_EXE%" "%~dp0main.py" %*
    exit /b %ERRORLEVEL%
)

:: 4. 检测是否已完成环境配置，未完成则拉起向导
if not exist "%~dp0.env" (
    "%PYTHON_EXE%" "%~dp0main.py" -init
)

:: 5. 交互式控制台菜单循环
:menu_loop
chcp 936 >nul 2>&1
cls
echo ====================================================================
echo             学搭子 (kassing-signin) 控制台管理面板                  
echo ====================================================================

set "HAS_TASK=0"
schtasks /query 2>nul | findstr /i "Kassing_" >nul 2>&1
if not errorlevel 1 set "HAS_TASK=1"

if "%HAS_TASK%"=="0" (
    echo   [当前状态] 尚未开启自动打卡
    echo              提示: 可输入 [5] 一键开启每天定时打卡
    goto :print_menu
)

if exist "%~dp0.pause" (
    echo   [当前状态] 自动打卡已开启 - 当前状态: 暂停打卡
    echo              提示: 到点将自动跳过，恢复打卡请按 [4]
    goto :print_menu
)

if exist "%~dp0.skip" (
    echo   [当前状态] 自动打卡已开启 - 当前状态: 跳过打卡生效中
    echo              提示: 下次打卡将自动跳过并递减，取消/恢复请按 [4]
    goto :print_menu
)

echo   [当前状态] 自动打卡已开启 - 当前状态: 正常运行中
echo              提示: 到点将自动打卡，放假调休暂停请按 [3]

:print_menu
echo --------------------------------------------------------------------
echo   【打卡服务】
echo     [1] 常规签到
echo     [2] 查看今日签到记录与状态
echo.
echo   【自动打卡与假期管理】
echo     [3] 暂停自动打卡
echo     [4] 恢复自动打卡
echo     [5] 开启 / 修改自动打卡时间
echo     [6] 关闭 / 卸载自动打卡任务
echo     [7] 查看自动打卡状态与运行日志
echo     [8] 跳过下次打卡
echo.
echo   【测试与演练工具】
echo     [9] 演练打卡全流程
echo    [10] 测试本地水印合成
echo    [11] 诊断账号状态与图库健康度
echo    [12] 测试系统定时器与调度健康度
echo.
echo   【设置与维护】
echo    [13] 重新运行配置向导
echo    [14] 检查并修复运行环境
echo.
echo     [0] 退出控制台
echo ====================================================================
set "choice="
set /p choice=请输入选项编号 [0-14]: 

if not defined choice goto :menu_loop

if "%choice%"=="1" cls & "%PYTHON_EXE%" "%~dp0main.py" & goto :end_action
if "%choice%"=="2" cls & "%PYTHON_EXE%" "%~dp0main.py" -records & goto :end_action
if "%choice%"=="3" cls & "%PYTHON_EXE%" "%~dp0main.py" -pause & goto :end_action
if "%choice%"=="4" cls & "%PYTHON_EXE%" "%~dp0main.py" -resume & goto :end_action
if "%choice%"=="5" cls & "%PYTHON_EXE%" "%~dp0main.py" -setup-cron & goto :end_action
if "%choice%"=="6" cls & "%PYTHON_EXE%" "%~dp0main.py" -remove-cron & goto :end_action
if "%choice%"=="7" cls & "%PYTHON_EXE%" "%~dp0main.py" -status & goto :end_action
if "%choice%"=="8" cls & "%PYTHON_EXE%" "%~dp0main.py" --skip-interactive & goto :end_action
if "%choice%"=="9" cls & "%PYTHON_EXE%" "%~dp0main.py" --dry-run & goto :end_action
if "%choice%"=="10" cls & "%PYTHON_EXE%" "%~dp0scripts\test_watermark.py" & goto :end_action
if "%choice%"=="11" cls & "%PYTHON_EXE%" "%~dp0scripts\check_status.py" & goto :end_action
if "%choice%"=="12" cls & "%PYTHON_EXE%" "%~dp0scripts\test_timer.py" & goto :end_action
if "%choice%"=="13" cls & "%PYTHON_EXE%" "%~dp0main.py" -init & goto :end_action
if "%choice%"=="14" goto :act_repair
if /i "%choice%"=="y" cls & "%PYTHON_EXE%" "%~dp0main.py" -y & goto :end_action
if /i "%choice%"=="-y" cls & "%PYTHON_EXE%" "%~dp0main.py" -y & goto :end_action
if "%choice%"=="0" exit /b 0
if /i "%choice%"=="q" exit /b 0

echo.
echo [提示] 输入无效，请输入 0 到 14 之间的数字。
goto :end_action

:act_repair
cls
echo ====================================================================
echo [*] 正在检查并自动安装 Python 依赖库 [requirements.txt] ...
echo ====================================================================
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
goto :end_action

:end_action
echo.
echo --------------------------------------------------------------------
echo 按任意键返回主菜单
pause >nul
goto :menu_loop
