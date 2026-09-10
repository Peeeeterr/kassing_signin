"""
定时任务自动化调度器 (scheduler.py)
实现跨平台 (Linux Crontab / Windows 任务计划程序) 定时打卡规则的自动化读写、生成与清理。
使用安全隔离标记块，绝对杜绝破坏或污染系统中的其他既有定时任务。
"""

import sys
import os
import re
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional

CRON_MARKER_START = "# >>> KASSING_SIGNIN_CRON >>>"
CRON_MARKER_END = "# <<< KASSING_SIGNIN_CRON <<<"
WINDOWS_TASK_PREFIX = "Kassing_"

DEFAULT_FALLBACK_SCHEDULES = [
    {"name": "早晨打卡", "time": "08:02", "delay": 180},
    {"name": "晚自习开始", "time": "18:18", "delay": 180},
    {"name": "晚自习结束", "time": "20:42", "delay": 180},
]

def parse_time_hh_mm(time_str: str) -> Optional[Tuple[int, int]]:
    """校验并解析 HH:MM 格式的时间字符串"""
    time_str = time_str.strip()
    match = re.match(r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$", time_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None

def compute_recommended_schedules(slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    根据官方 API 返回的时段列表，智能计算推荐的定时打卡时间点
    每个时段开始时间后推 2 分钟，规避整点蜂拥高并发与固定秒级特征
    """
    if not slots:
        return list(DEFAULT_FALLBACK_SCHEDULES)

    results = []
    for s in slots:
        name = s.get("name", "常规打卡")
        st_str = s.get("startTime", "")
        parsed = parse_time_hh_mm(st_str)
        if parsed:
            hour, minute = parsed
            dt = datetime(2000, 1, 1, hour, minute) + timedelta(minutes=2)
            rec_time = dt.strftime("%H:%M")
            results.append({
                "name": name,
                "time": rec_time,
                "delay": 180,
                "raw_start": st_str,
                "raw_end": s.get("endTime", "")
            })
        else:
            results.append({
                "name": name,
                "time": "08:02",
                "delay": 180,
                "raw_start": st_str,
                "raw_end": s.get("endTime", "")
            })

    return results if results else list(DEFAULT_FALLBACK_SCHEDULES)

# ==============================================================================
# Linux Crontab 管理逻辑
# ==============================================================================

def get_linux_crontab_content() -> str:
    """获取当前用户的全部 crontab 内容"""
    try:
        res = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return res.stdout
        return ""
    except Exception:
        return ""

def get_installed_linux_cron_lines() -> List[str]:
    """提取当前用户 crontab 中属于本项目的打卡规则"""
    content = get_linux_crontab_content()
    if not content or CRON_MARKER_START not in content:
        return []

    lines = content.splitlines()
    in_block = False
    result = []
    for line in lines:
        if line.strip() == CRON_MARKER_START:
            in_block = True
            continue
        if line.strip() == CRON_MARKER_END:
            in_block = False
            break
        if in_block and line.strip() and not line.strip().startswith("#"):
            result.append(line.strip())
    return result

def install_linux_cron(project_dir: str, schedules: List[Dict[str, Any]], days: str = "1-5") -> Tuple[bool, str]:
    """
    将打卡规则以安全隔离块的形式写入当前用户的 crontab
    :param project_dir: 项目绝对路径
    :param schedules: 包含 name, time ("HH:MM"), delay (秒) 的字典列表
    :param days: 星期过滤，默认 "1-5" (周一到周五)
    """
    run_script = os.path.join(project_dir, "run_cron.sh")
    if not os.path.exists(run_script):
        return False, f"未找到可执行的定时脚本: {run_script}"

    # 确保脚本有可执行权限
    try:
        os.chmod(run_script, 0o755)
    except Exception:
        pass

    old_crontab = get_linux_crontab_content()

    # 清除旧的标记块
    cleaned_lines = []
    in_block = False
    for line in old_crontab.splitlines():
        if line.strip() == CRON_MARKER_START:
            in_block = True
            continue
        if line.strip() == CRON_MARKER_END:
            in_block = False
            continue
        if not in_block:
            cleaned_lines.append(line)

    # 构造新的标记块
    new_block = [
        CRON_MARKER_START,
        "CRON_TZ=Asia/Shanghai"
    ]
    for item in schedules:
        name = item.get("name", "自动打卡")
        time_str = item.get("time", "08:00")
        delay = item.get("delay", 180)
        parsed = parse_time_hh_mm(time_str)
        if not parsed:
            continue
        hour, minute = parsed
        new_block.append(f"# {name} (设定时间: {time_str}，随机延时: {delay}秒，周期: {days})")
        new_block.append(f"{minute:02d} {hour:02d} * * {days} {run_script} {delay}")

    new_block.append(CRON_MARKER_END)

    # 组装完整的 crontab
    final_crontab = "\n".join(cleaned_lines).rstrip()
    if final_crontab:
        final_crontab += "\n\n"
    final_crontab += "\n".join(new_block) + "\n"

    try:
        res = subprocess.run(["crontab", "-"], input=final_crontab, text=True, capture_output=True, timeout=10)
        if res.returncode == 0:
            return True, "Linux Crontab 定时规则写入成功！"
        else:
            return False, f"Crontab 写入失败: {res.stderr.strip()}"
    except Exception as e:
        return False, f"执行 crontab 命令异常: {e}"

def uninstall_linux_cron() -> Tuple[bool, str]:
    """卸载并清理 Crontab 中属于本项目的规则块"""
    old_crontab = get_linux_crontab_content()
    if CRON_MARKER_START not in old_crontab:
        return True, "未检测到已安装的项目定时任务，无需清理。"

    cleaned_lines = []
    in_block = False
    for line in old_crontab.splitlines():
        if line.strip() == CRON_MARKER_START:
            in_block = True
            continue
        if line.strip() == CRON_MARKER_END:
            in_block = False
            continue
        if not in_block:
            cleaned_lines.append(line)

    final_crontab = "\n".join(cleaned_lines).strip()
    if final_crontab:
        final_crontab += "\n"

    try:
        if final_crontab:
            res = subprocess.run(["crontab", "-"], input=final_crontab, text=True, capture_output=True, timeout=10)
        else:
            res = subprocess.run(["crontab", "-r"], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return True, "Linux Crontab 定时规则已彻底清理。"
        else:
            return False, f"清理失败: {res.stderr.strip()}"
    except Exception as e:
        return False, f"执行清理异常: {e}"

# ==============================================================================
# Windows Task Scheduler 管理逻辑
# ==============================================================================

def get_installed_windows_tasks() -> List[str]:
    """查询 Windows 下已注册的打卡计划任务名称"""
    try:
        cmd = ["schtasks", "/query", "/fo", "list"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            return []
        found = []
        for line in res.stdout.splitlines():
            line_s = line.strip()
            if line_s.startswith("TaskName:") or line_s.startswith("任务名:"):
                tname = line_s.split(":", 1)[1].strip().lstrip("\\")
                if tname.startswith(WINDOWS_TASK_PREFIX):
                    found.append(tname)
        return found
    except Exception:
        return []

def install_windows_tasks(project_dir: str, schedules: List[Dict[str, Any]], days: str = "MON,TUE,WED,THU,FRI") -> Tuple[bool, str]:
    """
    通过 schtasks 命令为 Windows 注册静默后台定时任务
    """
    vbs_path = os.path.join(project_dir, "run_silent.vbs")
    if not os.path.exists(vbs_path):
        return False, f"未找到静默脚本: {vbs_path}"

    # 先清理历史任务
    uninstall_windows_tasks()

    created_tasks = []
    errors = []

    for idx, item in enumerate(schedules, 1):
        name = item.get("name", f"Slot_{idx}")
        time_str = item.get("time", "08:00")
        delay = item.get("delay", 180)
        task_name = f"{WINDOWS_TASK_PREFIX}Slot{idx}_{time_str.replace(':', '')}"

        # 命令使用 wscript.exe 调度 run_silent.vbs
        cmd = [
            "schtasks", "/create",
            "/tn", task_name,
            "/tr", f'wscript.exe "{vbs_path}" {delay}',
            "/sc", "weekly",
            "/d", days,
            "/st", time_str,
            "/f"
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                created_tasks.append(task_name)
            else:
                errors.append(f"{task_name} 创建失败: {res.stderr.strip() or res.stdout.strip()}")
        except Exception as e:
            errors.append(f"{task_name} 执行异常: {e}")

    if errors:
        return False, "; ".join(errors)
    return True, f"成功创建 {len(created_tasks)} 项 Windows 计划任务: {', '.join(created_tasks)}"

def uninstall_windows_tasks() -> Tuple[bool, str]:
    """卸载并删除所有以 Kassing_ 开头的 Windows 计划任务"""
    tasks = get_installed_windows_tasks()
    if not tasks:
        return True, "未检测到已安装的 Windows 打卡任务。"

    deleted = []
    errors = []
    for tname in tasks:
        try:
            cmd = ["schtasks", "/delete", "/tn", tname, "/f"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                deleted.append(tname)
            else:
                errors.append(f"删除 {tname} 失败: {res.stderr.strip()}")
        except Exception as e:
            errors.append(f"删除 {tname} 异常: {e}")

    if errors:
        return False, "; ".join(errors)
    return True, f"已清理 Windows 计划任务: {', '.join(deleted)}"

# ==============================================================================
# 统一跨平台管理调度接口
# ==============================================================================

def install_system_schedule(project_dir: str, schedules: List[Dict[str, Any]], workday_only: bool = True) -> Tuple[bool, str]:
    """跨平台写入系统定时任务"""
    if sys.platform.startswith("linux"):
        days = "1-5" if workday_only else "1-7"
        return install_linux_cron(project_dir, schedules, days=days)
    elif sys.platform.startswith("win"):
        days = "MON,TUE,WED,THU,FRI" if workday_only else "MON,TUE,WED,THU,FRI,SAT,SUN"
        return install_windows_tasks(project_dir, schedules, days=days)
    else:
        return False, f"暂不支持的操作系统平台: {sys.platform}"

def uninstall_system_schedule(project_dir: str) -> Tuple[bool, str]:
    """跨平台彻底清理系统定时任务"""
    if sys.platform.startswith("linux"):
        return uninstall_linux_cron()
    elif sys.platform.startswith("win"):
        return uninstall_windows_tasks()
    else:
        return False, f"暂不支持的操作系统平台: {sys.platform}"

def parse_cron_line_to_human(line: str) -> Optional[str]:
    """将单行 crontab 规则解析为通俗易懂的自然语言描述"""
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("CRON_TZ"):
        return None
    parts = line.split()
    if len(parts) < 5:
        return None
    minute, hour, dom, month, dow = parts[:5]
    try:
        h_int = int(hour)
        m_int = int(minute)
        time_str = f"{h_int:02d}:{m_int:02d}"
    except ValueError:
        time_str = f"{hour}:{minute}"

    if dow in ["1-5", "MON-FRI", "mon-fri"]:
        cycle_str = "工作日 (周一至周五)"
    elif dow in ["*", "1-7", "0-6", "0-7"]:
        cycle_str = "每天"
    elif dow in ["6,7", "0,6"]:
        cycle_str = "周末"
    else:
        cycle_str = f"周 {dow}"

    return f"{cycle_str} {time_str}"

def parse_windows_task_to_human(task_name: str) -> Optional[str]:
    """将 Windows 任务名解析为自然语言描述"""
    parts = task_name.split("_")
    if len(parts) >= 4:
        raw_time = parts[-1]
        if len(raw_time) == 4 and raw_time.isdigit():
            return f"定时打卡时间: {raw_time[:2]}:{raw_time[2:]}"
    return f"打卡任务: {task_name}"

def get_system_schedule_info() -> Dict[str, Any]:
    """获取当前系统中注册的打卡定时任务摘要（包含通俗易懂的自然语言表达）"""
    platform = "Linux (Crontab)" if sys.platform.startswith("linux") else ("Windows (Task Scheduler)" if sys.platform.startswith("win") else sys.platform)
    active_rules = []
    human_rules = []

    if sys.platform.startswith("linux"):
        active_rules = get_installed_linux_cron_lines()
        for r in active_rules:
            parsed = parse_cron_line_to_human(r)
            if parsed:
                human_rules.append(parsed)
    elif sys.platform.startswith("win"):
        active_rules = get_installed_windows_tasks()
        for r in active_rules:
            parsed = parse_windows_task_to_human(r)
            if parsed:
                human_rules.append(parsed)

    # 提取时间点摘要
    time_points = []
    cycle_name = "工作日 (周一至周五)"
    for hr in human_rules:
        if " " in hr:
            cycle, tm = hr.rsplit(" ", 1)
            time_points.append(tm)
            cycle_name = cycle
        elif ":" in hr:
            parts = hr.split(":")
            if len(parts) >= 2:
                time_points.append(parts[-2][-2:] + ":" + parts[-1][:2])

    has_configured = len(human_rules) > 0 or (len(active_rules) > 0 and not (len(active_rules) == 1 and active_rules[0].startswith("CRON_TZ")))

    return {
        "platform": platform,
        "is_configured": has_configured,
        "rules": active_rules,
        "human_rules": human_rules,
        "cycle_name": cycle_name,
        "time_points": sorted(list(set(time_points))) if time_points else []
    }
