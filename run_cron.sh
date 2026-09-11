#!/bin/bash
# ==============================================================================
# 学搭子定时打卡任务运行脚本 (run_cron.sh)
# 专为 Linux crontab 定时任务设计：
# 1. 自动定位脚本所在项目根目录并切换工作路径
# 2. 自动匹配虚拟环境 Python 解释器
# 3. 随机防风控抖动延迟 (10 ~ 180 秒)，杜绝固定秒级打卡特征
# 4. 自动记录带时间戳的完整日志到 logs/cron.log
# ==============================================================================

# 定位项目根目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

# 创建日志目录
mkdir -p "$PROJECT_DIR/logs"
LOG_FILE="$PROJECT_DIR/logs/cron.log"

# 检查是否存在调休/节假日暂停标识文件 (.pause)
if [ -f "$PROJECT_DIR/.pause" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Cron] 检测到 .pause 暂停标识文件，跳过本次打卡任务。" >> "$LOG_FILE"
    exit 0
fi

# 随机防风控延时与参数解析:
# 1. 默认范围: 10 ~ 180 秒 (约 3 分钟)
# 2. 支持传入 --immediate: 跳过随机等待立即执行 (用于测试与手动触发)
# 3. 支持额外参数透传 (如 --dry-run)
DO_WAIT=1
MAX_DELAY=180
EXTRA_ARGS=()

for arg in "$@"; do
    if [ "$arg" = "--immediate" ]; then
        DO_WAIT=0
    elif [[ "$arg" =~ ^[0-9]+$ ]] && [ "$DO_WAIT" -eq 1 ]; then
        MAX_DELAY="$arg"
    else
        EXTRA_ARGS+=("$arg")
    fi
done

if [ "$DO_WAIT" -eq 0 ]; then
    RANDOM_DELAY=0
else
    MIN_DELAY=10
    if [ "$MAX_DELAY" -le "$MIN_DELAY" ]; then
        RANDOM_DELAY=$MAX_DELAY
    else
        SPAN=$((MAX_DELAY - MIN_DELAY))
        RANDOM_DELAY=$((MIN_DELAY + RANDOM % SPAN))
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Cron] 触发定时打卡 (最大窗口: ${MAX_DELAY}s)，随机等待: ${RANDOM_DELAY} 秒..." >> "$LOG_FILE"
    sleep "$RANDOM_DELAY"
fi

# 寻找 Python 解释器 (优先探测：.env 指定 > 本地虚拟环境 > Conda 环境 > 系统默认)
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
    # 尝试探测常见 Conda 默认路径与系统 Python
    for candidate in \
        "$HOME/anaconda3/bin/python" \
        "$HOME/miniconda3/bin/python" \
        "$(which python3 2>/dev/null)" \
        "/usr/bin/python3"; do
        if [ -x "$candidate" ]; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi

echo "========================================================" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始执行自动打卡任务..." >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 运行解释器: ${PYTHON_BIN:-未找到}" >> "$LOG_FILE"

# 运行主程序 (-y 跳过交互式倒计时，并透传附加参数)
"$PYTHON_BIN" "$PROJECT_DIR/main.py" -y "${EXTRA_ARGS[@]}" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 任务执行完毕，退出码: $EXIT_CODE" >> "$LOG_FILE"
echo "========================================================" >> "$LOG_FILE"

exit $EXIT_CODE
