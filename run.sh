#!/bin/bash
# ==============================================================================
# 学搭子自动化打卡助手统一交互控制台与启动脚本 (run.sh)
# 核心功能:
#   1. 运行环境自检：自动探测 Python 解释器并自动安装缺失的依赖库；
#   2. 首次运行引导：若未检测到 .env 自动无缝拉起初始化配置向导；
#   3. 全功能交互菜单：无参数运行时弹出友好数字菜单，直观调用各项功能；
#   4. 命令行直通透传：带参数运行时直接透明转发执行，不弹菜单干扰脚本自动化。
# ==============================================================================

# 定位脚本所在项目根目录并切换
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

# 1. 探测 Python 解释器
if [ -n "$PYTHON_BIN" ] && [ -x "$PYTHON_BIN" ]; then
    : # 环境变量已预先指定
elif [ -f "$PROJECT_DIR/.env" ] && grep -q "^PYTHON_BIN=" "$PROJECT_DIR/.env"; then
    PYTHON_BIN=$(grep "^PYTHON_BIN=" "$PROJECT_DIR/.env" | cut -d '=' -f2- | tr -d '"' | tr -d "'" | tr -d ' ')
elif [ -f "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
elif [ -f "$PROJECT_DIR/venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
elif [ -n "$CONDA_PREFIX" ] && [ -f "$CONDA_PREFIX/bin/python" ]; then
    PYTHON_BIN="$CONDA_PREFIX/bin/python"
elif [ -n "$VIRTUAL_ENV" ] && [ -f "$VIRTUAL_ENV/bin/python" ]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
else
    for candidate in \
        "$HOME/anaconda3/bin/python" \
        "$HOME/miniconda3/bin/python" \
        "$(which python3 2>/dev/null)" \
        "/usr/bin/python3" \
        "$(which python 2>/dev/null)"; do
        if [ -x "$candidate" ]; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi

if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
    echo "[错误] 未检测到可用的 Python 解释器，请先安装 Python 3.9+ 或激活虚拟环境。"
    exit 1
fi

# 2. 检查核心依赖库并在首次运行时自动安装
install_dependencies() {
    echo "===================================================================="
    echo "[*] 正在检查并自动安装 Python 依赖库 (requirements.txt)..."
    echo "===================================================================="
    "$PYTHON_BIN" -m pip install -r "$PROJECT_DIR/requirements.txt"
    if [ $? -eq 0 ]; then
        echo "[+] 依赖环境准备完毕！"
    else
        echo "[-] 依赖安装失败，请检查网络连接或尝试手动配置镜像源。"
    fi
}

if ! "$PYTHON_BIN" -c "import requests, PIL" 2>/dev/null; then
    install_dependencies
fi

# 3. 若用户在命令行携带了参数 (如 ./run.sh -y, ./run.sh -status)，直接透传执行
if [ $# -gt 0 ]; then
    exec "$PYTHON_BIN" "$PROJECT_DIR/main.py" "$@"
fi

# 4. 检测是否首次运行 (.env 是否存在)，不存在则拉起初始化向导
if [ ! -f "$PROJECT_DIR/.env" ]; then
    if "$PYTHON_BIN" -c "import requests, PIL" 2>/dev/null; then
        "$PYTHON_BIN" "$PROJECT_DIR/main.py" -init
    fi
fi

# 5. 交互式控制台菜单循环 (纯 Shell 原生实现，即使 Python 依赖异常亦可调用修复)
while true; do
    clear 2>/dev/null || echo ""
    echo "===================================================================="
    echo "            学搭子 (kassing-signin) 控制台管理面板                  "
    echo "===================================================================="

    # 检测系统底层 Crontab 是否已注册本项目规则
    has_cron=0
    if crontab -l 2>/dev/null | grep -q "KASSING_SIGNIN_CRON"; then
        has_cron=1
    fi

    if [ "$has_cron" -eq 0 ]; then
        echo "  [当前状态] 尚未开启自动打卡"
        echo "             提示: 可输入 [5] 一键开启每天定时打卡"
    elif [ -f "$PROJECT_DIR/.pause" ]; then
        echo "  [当前状态] 自动打卡已开启 | 当前状态: 暂停打卡"
        echo "             提示: 到点将自动跳过，恢复打卡请按 [4]"
    elif [ -f "$PROJECT_DIR/.skip" ]; then
        echo "  [当前状态] 自动打卡已开启 | 当前状态: 跳过打卡生效中"
        echo "             提示: 下次打卡将自动跳过并递减，取消/恢复请按 [4]"
    else
        echo "  [当前状态] 自动打卡已开启 | 当前状态: 正常运行中"
        echo "             提示: 到点将自动打卡，放假调休暂停请按 [3]"
    fi
    echo "--------------------------------------------------------------------"
    echo "  【打卡服务】"
    echo "    [1] 常规签到"
    echo "    [2] 查看今日签到记录与状态"
    echo ""
    echo "  【自动打卡与假期管理】"
    echo "    [3] 暂停自动打卡"
    echo "    [4] 恢复自动打卡"
    echo "    [5] 开启 / 修改自动打卡时间"
    echo "    [6] 关闭 / 卸载自动打卡任务"
    echo "    [7] 查看自动打卡状态与运行日志"
    echo "    [8] 跳过下次打卡"
    echo ""
    echo "  【测试与演练工具】"
    echo "    [9] 演练打卡全流程"
    echo "   [10] 测试本地水印合成"
    echo "   [11] 诊断账号状态与图库健康度"
    echo "   [12] 测试系统定时器与调度健康度"
    echo ""
    echo "  【设置与维护】"
    echo "   [13] 重新运行配置向导"
    echo "   [14] 检查并修复运行环境"
    echo ""
    echo "    [0] 退出控制台"
    echo "===================================================================="
    read -r -p "请输入选项编号 [0-14]: " choice

    case "$choice" in
        1)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/main.py"
            ;;
        2)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/main.py" -records
            ;;
        3)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/main.py" -pause
            ;;
        4)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/main.py" -resume
            ;;
        5)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/main.py" -setup-cron
            ;;
        6)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/main.py" -remove-cron
            ;;
        7)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/main.py" -status
            ;;
        8)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/main.py" --skip-interactive
            ;;
        9)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/main.py" --dry-run
            ;;
        10)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/scripts/test_watermark.py"
            ;;
        11)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/scripts/check_status.py"
            ;;
        12)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/scripts/test_timer.py"
            ;;
        13)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/main.py" -init
            ;;
        14)
            echo ""
            install_dependencies
            ;;
        y|Y|-y)
            echo ""
            "$PYTHON_BIN" "$PROJECT_DIR/main.py" -y
            ;;
        0|q|Q)
            echo ""
            echo "[*] 已安全退出控制台。"
            exit 0
            ;;
        *)
            echo ""
            echo "[提示] 输入无效，请输入 0 到 14 之间的数字选项。"
            ;;
    esac

    echo ""
    echo "--------------------------------------------------------------------"
    read -r -p "按回车键返回主菜单..." dummy
done
