"""
定时任务自动化调度器 (scheduler.py)
实现跨平台 (Linux Crontab / Windows 任务计划程序) 定时打卡规则的自动化读写、生成与清理。
使用安全隔离标记块，绝对杜绝破坏或污染系统中的其他既有定时任务。
"""

import sys
import os
import json
import re
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

CRON_MARKER_START = "# >>> KASSING_SIGNIN_CRON >>>"
CRON_MARKER_END = "# <<< KASSING_SIGNIN_CRON <<<"
WINDOWS_TASK_PREFIX = "Kassing_"
SKIP_FILE_NAME = ".skip"

DEFAULT_FALLBACK_SCHEDULES = [
    {"name": "早晨打卡", "time": "08:00", "delay": 180},
    {"name": "晚自习开始", "time": "18:17", "delay": 180},
    {"name": "晚自习结束", "time": "20:42", "delay": 180},
]

def get_skip_file(project_dir: Optional[str] = None) -> str:
    base = project_dir or PROJECT_ROOT
    return os.path.join(base, SKIP_FILE_NAME)

def get_skip_count(project_dir: Optional[str] = None) -> int:
    """
    获取当前设定的跳过打卡剩余次数
    :return: 剩余跳过次数，未设置或已过期则返回 0
    """
    sf = get_skip_file(project_dir)
    if not os.path.exists(sf):
        return 0
    try:
        with open(sf, "r", encoding="utf-8") as f:
            data = json.load(f)
            return max(0, int(data.get("count", 0)))
    except Exception:
        try:
            with open(sf, "r", encoding="utf-8") as f:
                return max(0, int(f.read().strip()))
        except Exception:
            return 0

def set_skip_count(count: int = 1, project_dir: Optional[str] = None) -> bool:
    """
    设定跳过打卡任务
    :param count: 跳过打卡次数，默认为 1 (跳过单次打卡)
    :param project_dir: 项目根目录
    :return: 是否设置成功
    """
    if count < 1:
        cancel_skip(project_dir)
        return False

    sf = get_skip_file(project_dir)
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "count": int(count),
            "created_at": now_str,
            "updated_at": now_str,
        }
        with open(sf, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def cancel_skip(project_dir: Optional[str] = None) -> bool:
    """
    取消已设定的跳过打卡任务
    :param project_dir: 项目根目录
    :return: 是否取消成功
    """
    sf = get_skip_file(project_dir)
    if os.path.exists(sf):
        try:
            os.remove(sf)
            return True
        except Exception:
            return False
    return True

def consume_skip(project_dir: Optional[str] = None) -> Tuple[bool, int]:
    """
    打卡触发时消耗 1 次跳过配额
    :param project_dir: 项目根目录
    :return: (是否成功跳过本次打卡, 剩余跳过次数)
    """
    count = get_skip_count(project_dir)
    if count <= 0:
        cancel_skip(project_dir)
        return False, 0

    new_count = count - 1
    sf = get_skip_file(project_dir)
    if new_count > 0:
        try:
            data = {
                "count": new_count,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(sf, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    else:
        cancel_skip(project_dir)

    return True, new_count

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
    默认推荐时间序列: 08:00, 18:17, 20:42
    """
    if not slots:
        return list(DEFAULT_FALLBACK_SCHEDULES)

    # 预设推荐时间点
    default_times = ["08:00", "18:17", "20:42"]

    results = []
    for idx, s in enumerate(slots):
        name = s.get("name", f"打卡时段_{idx+1}")
        st_str = s.get("startTime", "")
        if idx < len(default_times):
            rec_time = default_times[idx]
        else:
            parsed = parse_time_hh_mm(st_str)
            if parsed:
                hour, minute = parsed
                dt = datetime(2000, 1, 1, hour, minute) + timedelta(minutes=2)
                rec_time = dt.strftime("%H:%M")
            else:
                rec_time = "08:00"

        results.append({
            "name": name,
            "time": rec_time,
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

from kassing_signin.config import get_beijing_now, BEIJING_TZ

def get_installed_linux_cron_lines() -> List[str]:
    """提取当前用户 crontab 中属于本项目的打卡规则 (纯规则行)"""
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

def get_installed_linux_cron_rules() -> List[Dict[str, Any]]:
    """
    结构化提取当前用户 crontab 中属于本项目的打卡规则
    包含注释中的时段名称、防风控随机延时、周期及下次预计触发时间
    """
    content = get_linux_crontab_content()
    if not content or CRON_MARKER_START not in content:
        return []

    lines = content.splitlines()
    in_block = False
    rules = []
    last_comment = ""

    for line in lines:
        sline = line.strip()
        if sline == CRON_MARKER_START:
            in_block = True
            continue
        if sline == CRON_MARKER_END:
            in_block = False
            break
        if not in_block or not sline:
            continue

        if sline.startswith("#"):
            # 记录注释内容，形如: # 早晨打卡 (设定时间: 08:02，随机延时: 180秒，周期: 1-5)
            last_comment = sline.lstrip("#").strip()
            continue

        if sline.startswith("CRON_TZ"):
            continue

        # 解析具体的 cron 行
        parts = sline.split()
        if len(parts) >= 5:
            rule_info = parse_cron_rule_details(sline, comment=last_comment)
            rules.append(rule_info)
            last_comment = ""

    return rules

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
        res = subprocess.run(cmd, capture_output=True, timeout=10)
        try:
            out_text = res.stdout.decode('utf-8')
        except UnicodeDecodeError:
            out_text = res.stdout.decode('gbk', errors='ignore')
        
        if res.returncode != 0:
            return []
        found = []
        for line in out_text.splitlines():
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
            res = subprocess.run(cmd, capture_output=True, timeout=10)
            try:
                out_text = res.stdout.decode('utf-8')
                err_text = res.stderr.decode('utf-8')
            except UnicodeDecodeError:
                out_text = res.stdout.decode('gbk', errors='ignore')
                err_text = res.stderr.decode('gbk', errors='ignore')
            
            if res.returncode == 0:
                created_tasks.append(task_name)
            else:
                errors.append(f"{task_name} 创建失败: {err_text.strip() or out_text.strip()}")
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
            res = subprocess.run(cmd, capture_output=True, timeout=10)
            try:
                err_text = res.stderr.decode('utf-8')
            except UnicodeDecodeError:
                err_text = res.stderr.decode('gbk', errors='ignore')
                
            if res.returncode == 0:
                deleted.append(tname)
            else:
                errors.append(f"删除 {tname} 失败: {err_text.strip()}")
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

def parse_dow_to_human(dow: str) -> str:
    """将 Crontab / 星期规则转换为通俗易懂的中文描述"""
    dow_clean = dow.strip().upper()
    if dow_clean in ["*", "1-7", "0-6", "0-7"]:
        return "每天"
    if dow_clean in ["1-5", "MON-FRI", "MON,TUE,WED,THU,FRI"]:
        return "每周一至周五"
    if dow_clean in ["6,7", "7,6", "0,6", "6,0", "6-7", "SAT,SUN"]:
        return "周末"
    if dow_clean in ["1-6", "MON-SAT"]:
        return "每周一至周六"

    day_map = {
        "1": "周一", "MON": "周一",
        "2": "周二", "TUE": "周二",
        "3": "周三", "WED": "周三",
        "4": "周四", "THU": "周四",
        "5": "周五", "FRI": "周五",
        "6": "周六", "SAT": "周六",
        "7": "周日", "0": "周日", "SUN": "周日",
    }

    parts = [p.strip() for p in dow_clean.split(",") if p.strip()]
    if parts and all(p in day_map for p in parts):
        return "每周" + "、".join(day_map[p] for p in parts)

    return f"每周 {dow}"

def calculate_next_run(hour: int, minute: int, dow: str = "1-5") -> Tuple[Optional[datetime], str]:
    """
    根据北京时间计算指定时段的下一次预计触发时刻及距今倒计时描述
    """
    now_cst = get_beijing_now()
    dow_clean = dow.strip().upper()

    # 确定允许的星期集合 (cron 规范: 1=Mon, 2=Tue, ..., 5=Fri, 6=Sat, 7=Sun, 0=Sun)
    allowed_days = set()
    if dow_clean in ["*", "1-7", "0-6", "0-7"]:
        allowed_days = {0, 1, 2, 3, 4, 5, 6, 7}
    elif dow_clean in ["1-5", "MON-FRI", "MON,TUE,WED,THU,FRI"]:
        allowed_days = {1, 2, 3, 4, 5}
    elif dow_clean in ["6,7", "7,6", "0,6", "6,0", "6-7", "SAT,SUN"]:
        allowed_days = {0, 6, 7}
    elif dow_clean in ["1-6", "MON-SAT"]:
        allowed_days = {1, 2, 3, 4, 5, 6}
    else:
        day_val_map = {
            "1": 1, "MON": 1, "2": 2, "TUE": 2, "3": 3, "WED": 3,
            "4": 4, "THU": 4, "5": 5, "FRI": 5, "6": 6, "SAT": 6,
            "7": 7, "0": 7, "SUN": 7
        }
        for p in dow_clean.split(","):
            p_s = p.strip()
            if p_s in day_val_map:
                allowed_days.add(day_val_map[p_s])
                if day_val_map[p_s] == 7:
                    allowed_days.add(0)

    if not allowed_days:
        allowed_days = {1, 2, 3, 4, 5}

    # 逐日推算未来 8 天内的候选触发时间
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    for day_offset in range(8):
        cand_date = now_cst.date() + timedelta(days=day_offset)
        # Python: 0=Mon, ..., 6=Sun -> cron: 1..7
        py_wd = cand_date.weekday()
        cron_wd = py_wd + 1

        if (cron_wd in allowed_days) or (cron_wd == 7 and 0 in allowed_days):
            cand_dt = datetime(cand_date.year, cand_date.month, cand_date.day, hour, minute, 0, tzinfo=BEIJING_TZ)
            if cand_dt > now_cst:
                delta = cand_dt - now_cst
                secs = int(delta.total_seconds())
                hrs = secs // 3600
                mins = (secs % 3600) // 60

                if day_offset == 0:
                    day_prefix = "今天"
                elif day_offset == 1:
                    day_prefix = "明天"
                elif day_offset == 2:
                    day_prefix = "后天"
                else:
                    day_prefix = f"{cand_date.strftime('%m月%d日')} {weekday_cn[py_wd]}"

                wait_desc = f"约 {hrs} 小时 {mins} 分钟后" if hrs > 0 else f"约 {mins} 分钟后"
                time_display = cand_dt.strftime('%H:%M')
                return cand_dt, f"{day_prefix} {time_display}，{wait_desc}"

    return None, "按设定周期触发"

def parse_cron_rule_details(line: str, comment: Optional[str] = None) -> Dict[str, Any]:
    """
    全面解析单行 Crontab 规则，生成丰富的人性化语义字典
    """
    line = line.strip()
    parts = line.split()
    if len(parts) < 5:
        return {"raw_line": line, "human_desc": line}

    minute_s, hour_s, dom_s, month_s, dow_s = parts[:5]
    delay_s = parts[-1] if len(parts) >= 7 and parts[-1].isdigit() else "180"

    try:
        hour = int(hour_s)
        minute = int(minute_s)
        time_str = f"{hour:02d}:{minute:02d}"
    except ValueError:
        hour = 8
        minute = 2
        time_str = f"{hour_s}:{minute_s}"

    cycle_desc = parse_dow_to_human(dow_s)

    # 尝试从前置注释提取时段名
    slot_name = "自动打卡"
    if comment:
        clean_c = comment.strip()
        if "(" in clean_c:
            slot_name = clean_c.split("(", 1)[0].strip()
        elif " " in clean_c:
            slot_name = clean_c.split()[0].strip()
        else:
            slot_name = clean_c

    next_dt, next_str = calculate_next_run(hour, minute, dow_s)
    human_desc = f"【{slot_name}】 {cycle_desc} {time_str}"

    return {
        "slot_name": slot_name,
        "time": time_str,
        "hour": hour,
        "minute": minute,
        "dow": dow_s,
        "delay": int(delay_s) if delay_s.isdigit() else 180,
        "cycle_desc": cycle_desc,
        "human_desc": human_desc,
        "next_run_dt": next_dt,
        "next_run_str": next_str,
        "raw_line": line,
        "comment": comment or ""
    }

def parse_cron_line_to_human(line: str) -> Optional[str]:
    """将单行 crontab 规则解析为通俗易懂的自然语言描述"""
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("CRON_TZ"):
        return None
    details = parse_cron_rule_details(line)
    return details.get("human_desc")

def parse_windows_task_to_human(task_name: str) -> Dict[str, Any]:
    """将 Windows 任务名解析为自然语言描述并推算下次触发"""
    parts = task_name.split("_")
    slot_name = "自动打卡"
    time_str = "--:--"
    hour = 8
    minute = 0
    next_dt = None
    next_str = "按系统计划触发"

    # 任务命名格式例如: Kassing_Slot1_0802
    if len(parts) >= 3:
        slot_tag = parts[1]
        raw_time = parts[-1]
        slot_name = f"打卡时段 {slot_tag}"
        if len(raw_time) == 4 and raw_time.isdigit():
            hour = int(raw_time[:2])
            minute = int(raw_time[2:])
            time_str = f"{hour:02d}:{minute:02d}"
            next_dt, next_str = calculate_next_run(hour, minute, "1-5")

    human_desc = f"【{slot_name}】 每周一至周五 {time_str}"

    return {
        "slot_name": slot_name,
        "time": time_str,
        "hour": hour,
        "minute": minute,
        "cycle_desc": "每周一至周五",
        "human_desc": human_desc,
        "next_run_dt": next_dt,
        "next_run_str": next_str,
        "task_name": task_name
    }

def get_system_schedule_info() -> Dict[str, Any]:
    """获取当前系统中注册的打卡定时任务摘要（包含通俗易懂的自然语言表达与下次预计触发时间）"""
    is_linux = sys.platform.startswith("linux")
    is_win = sys.platform.startswith("win")
    platform = "Linux Crontab" if is_linux else ("Windows 任务计划" if is_win else sys.platform)

    rules_detail = []
    human_rules = []
    time_points = []
    cycle_name = "每周一至周五"

    if is_linux:
        rules_detail = get_installed_linux_cron_rules()
        for r in rules_detail:
            human_rules.append(r["human_desc"])
            if r.get("time"):
                time_points.append(r["time"])
            if r.get("cycle_desc"):
                cycle_name = r["cycle_desc"]
    elif is_win:
        active_tasks = get_installed_windows_tasks()
        for tname in active_tasks:
            parsed = parse_windows_task_to_human(tname)
            rules_detail.append(parsed)
            human_rules.append(parsed["human_desc"])
            if parsed.get("time") and parsed["time"] != "--:--":
                time_points.append(parsed["time"])

    # 计算最临近的下一次打卡触发
    nearest_next_run = "暂无计划"
    if rules_detail:
        valid_nexts = [r for r in rules_detail if r.get("next_run_dt")]
        if valid_nexts:
            valid_nexts.sort(key=lambda x: x["next_run_dt"])
            nearest = valid_nexts[0]
            nearest_next_run = f"{nearest['slot_name']}: {nearest['next_run_str']}"
        else:
            nearest_next_run = rules_detail[0].get("next_run_str", "暂无计划")

    has_configured = len(rules_detail) > 0

    return {
        "platform": platform,
        "is_configured": has_configured,
        "rules_count": len(rules_detail),
        "rules_detail": rules_detail,
        "human_rules": human_rules,
        "cycle_name": cycle_name,
        "time_points": sorted(list(set(time_points))) if time_points else [],
        "nearest_next_run": nearest_next_run
    }

def check_daemon_status() -> Dict[str, Any]:
    """检查操作系统定时服务守护进程是否处于正常运行状态"""
    is_linux = sys.platform.startswith("linux")
    is_win = sys.platform.startswith("win")

    if is_linux:
        # 1. 尝试使用 systemctl 检测
        for svc in ["cron", "crond"]:
            try:
                res = subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True, timeout=3)
                if res.returncode == 0 and res.stdout.strip() == "active":
                    return {
                        "is_active": True,
                        "service_name": svc,
                        "status_text": "正在运行",
                        "advice": "系统定时守护进程运行正常。"
                    }
            except Exception:
                pass

        # 2. 尝试 service / etc/init.d 检测 (常见于 WSL, Docker 或非 systemd 环境)
        try:
            res = subprocess.run(["service", "cron", "status"], capture_output=True, text=True, timeout=3)
            out = (res.stdout + res.stderr).lower()
            if "running" in out or "is running" in out:
                return {
                    "is_active": True,
                    "service_name": "cron",
                    "status_text": "正在运行",
                    "advice": "系统定时守护进程运行正常。"
                }
        except Exception:
            pass

        # 3. 检查进程表是否存在 cron/crond 进程
        try:
            res = subprocess.run(["pgrep", "-x", "cron"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                return {
                    "is_active": True,
                    "service_name": "cron",
                    "status_text": "正在运行",
                    "advice": "系统定时守护进程运行正常。"
                }
        except Exception:
            pass

        return {
            "is_active": False,
            "service_name": "cron / crond",
            "status_text": "未运行",
            "advice": "系统 Cron 定时服务未在运行！在 Linux/WSL 下定时任务将无法自动触发。\n"
                      "    修复方式：在终端执行 [sudo systemctl start cron] 或 [sudo service cron start] 启动服务。"
        }

    elif is_win:
        try:
            res = subprocess.run(["sc", "query", "Schedule"], capture_output=True, timeout=5)
            try:
                out_text = res.stdout.decode('utf-8')
            except UnicodeDecodeError:
                out_text = res.stdout.decode('gbk', errors='ignore')
                
            if "RUNNING" in out_text:
                return {
                    "is_active": True,
                    "service_name": "Task Scheduler",
                    "status_text": "正在运行",
                    "advice": "Windows 任务计划程序服务运行正常。"
                }
            else:
                return {
                    "is_active": False,
                    "service_name": "Task Scheduler",
                    "status_text": "未运行或已停止",
                    "advice": "Windows 任务计划程序服务未在运行！请在服务管理 (services.msc) 中启动 Task Scheduler 服务。"
                }
        except Exception as e:
            return {
                "is_active": True,
                "service_name": "Task Scheduler",
                "status_text": f"检测受限: {e}",
                "advice": "未能直接获取服务状态，默认视作正常。"
            }

    return {
        "is_active": False,
        "service_name": sys.platform,
        "status_text": "未知平台",
        "advice": f"当前操作系统平台 {sys.platform} 暂无专属守护进程检测。"
    }

def check_system_clock_sync() -> Dict[str, Any]:
    """检查本地系统时钟与北京时间 (UTC+8) 是否保持同步及是否存在时区偏差"""
    local_now = datetime.now()
    cst_now = get_beijing_now()

    local_tz_offset_hours = round((datetime.now() - datetime.utcnow()).total_seconds() / 3600.0)
    local_str = local_now.strftime("%Y-%m-%d %H:%M:%S")
    cst_str = cst_now.strftime("%Y-%m-%d %H:%M:%S")
    time_diff_secs = abs((local_now.replace(tzinfo=None) - cst_now.replace(tzinfo=None)).total_seconds())

    is_synced = True
    advice = "系统时钟与北京时间保持一致。"

    if local_tz_offset_hours != 8:
        is_synced = False
        advice = (
            f"检测到系统本地时区为 UTC{local_tz_offset_hours:+d} (非北京时间 UTC+8)！\n"
            "    若 Linux crontab 所在系统不支持 CRON_TZ 环境变量，定时任务可能按当地时钟触发导致时差偏差。\n"
            "    建议：可在 Linux 中执行 [sudo timedatectl set-timezone Asia/Shanghai] 将时区同步为北京时间。"
        )
    elif time_diff_secs > 120:
        is_synced = False
        advice = (
            f"检测到系统时钟与标准时间相差 {int(time_diff_secs)} 秒！\n"
            "    时钟漂移可能导致打卡在时段截止后才被触发。\n"
            "    建议：同步系统网络时间 (NTP)。"
        )

    return {
        "is_synced": is_synced,
        "local_time": local_str,
        "cst_time": cst_str,
        "tz_offset_hours": local_tz_offset_hours,
        "diff_seconds": int(time_diff_secs),
        "advice": advice
    }

def diagnose_timer_system(project_dir: str) -> Dict[str, Any]:
    """
    全方位对系统定时打卡进行健康诊断
    涵盖：守护进程状态、定时规则解析、时钟时区、脚本执行权限、虚拟环境解释器、暂停状态与历史日志
    """
    daemon_info = check_daemon_status()
    clock_info = check_system_clock_sync()
    sched_info = get_system_schedule_info()

    issues = []
    warnings = []
    good_points = []

    # 1. 守护进程检测
    if not daemon_info["is_active"]:
        issues.append(f"守护进程异常: {daemon_info['service_name']} {daemon_info['status_text']}。\n    -> {daemon_info['advice']}")
    else:
        good_points.append(f"系统定时服务: {daemon_info['service_name']} 正常运行中")

    # 2. 定时规则配置检测
    if not sched_info["is_configured"]:
        issues.append("未在系统中检测到打卡定时任务。请在控制台运行 [5] 一键开启/设置定时打卡。")
    else:
        good_points.append(f"定时打卡规则: 已注册 {sched_info['rules_count']} 项打卡任务，周期: {sched_info['cycle_name']}")

    # 3. 时区时钟检测
    if not clock_info["is_synced"]:
        warnings.append(f"时区/时钟提示: {clock_info['advice']}")
    else:
        good_points.append("系统时区与时钟: 与东八区北京时间精准同步")

    # 4. 关键脚本权限与存在性
    is_linux = sys.platform.startswith("linux")
    if is_linux:
        cron_sh = os.path.join(project_dir, "run_cron.sh")
        if not os.path.exists(cron_sh):
            issues.append(f"缺失定时任务主脚本: {cron_sh}")
        elif not os.access(cron_sh, os.X_OK):
            try:
                os.chmod(cron_sh, 0o755)
                good_points.append("定时脚本权限: 已自动修复 run_cron.sh 可执行权限")
            except Exception:
                issues.append(f"run_cron.sh 缺少执行权限，请在终端执行: chmod +x {cron_sh}")
        else:
            good_points.append("定时脚本权限: run_cron.sh 具备可执行权限")
    else:
        vbs_path = os.path.join(project_dir, "run_silent.vbs")
        bat_path = os.path.join(project_dir, "run_windows.bat")
        if not os.path.exists(vbs_path) or not os.path.exists(bat_path):
            issues.append(f"缺失 Windows 定时脚本: {bat_path} 或 {vbs_path}")
        else:
            good_points.append("定时脚本状态: run_windows.bat 与 run_silent.vbs 完整就绪")

    # 5. Python 解释器与依赖校验
    env_file = os.path.join(project_dir, ".env")
    py_bin = sys.executable
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip().startswith("PYTHON_BIN="):
                    val = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    if val and os.path.exists(val):
                        py_bin = val
                    break

    try:
        chk_res = subprocess.run([py_bin, "-c", "import requests, PIL; print('OK')"], capture_output=True, text=True, timeout=5)
        if chk_res.returncode == 0 and "OK" in chk_res.stdout:
            good_points.append(f"Python 运行环境: {py_bin}，核心依赖校验通过")
        else:
            warnings.append(f"Python 解释器 {py_bin} 依赖检查异常: {chk_res.stderr.strip() or '缺失依赖'}")
    except Exception as e:
        warnings.append(f"调用 Python 解释器 {py_bin} 失败: {e}")

    # 6. 暂停文件检测
    pause_file = os.path.join(project_dir, ".pause")
    is_paused = os.path.exists(pause_file)
    if is_paused:
        warnings.append("当前处于【暂停打卡】状态！到达设定时间将自动跳过。如需恢复请在控制台按 [4] 恢复。")
    else:
        good_points.append("运行开关状态: 正常开启中")

    # 7. 跳过打卡设置检测
    skip_count = get_skip_count(project_dir)
    if skip_count > 0:
        warnings.append(f"当前已设定【跳过打卡】，剩余跳过次数: {skip_count} 次！下次到达设定时间将自动跳过。")

    # 8. 最近日志检查
    log_file = os.path.join(project_dir, "logs", "cron.log")
    last_log_snippet = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                last_log_snippet = lines[-6:] if lines else []
        except Exception:
            pass

    overall_healthy = (len(issues) == 0)

    return {
        "overall_healthy": overall_healthy,
        "is_paused": is_paused,
        "skip_count": skip_count,
        "daemon": daemon_info,
        "clock": clock_info,
        "schedule": sched_info,
        "good_points": good_points,
        "warnings": warnings,
        "issues": issues,
        "last_log_snippet": last_log_snippet
    }

def test_timer_execution(project_dir: str, dry_run: bool = True) -> Dict[str, Any]:
    """
    仿真触发测试系统定时打卡脚本链路
    通过直接调用 run_cron.sh / run_windows.bat 的 --immediate 模式进行全链路测试，
    验证定时触发脚本是否能顺利唤起 Python、写出日志并完成执行。
    """
    is_linux = sys.platform.startswith("linux")
    log_file = os.path.join(project_dir, "logs", "cron.log")

    init_size = os.path.getsize(log_file) if os.path.exists(log_file) else 0

    if is_linux:
        script = os.path.join(project_dir, "run_cron.sh")
        cmd = [script, "--immediate"]
        if dry_run:
            cmd.append("--dry-run")
    else:
        script = os.path.join(project_dir, "run_windows.bat")
        cmd = [script, "--immediate"]
        if dry_run:
            cmd.append("--dry-run")

    try:
        proc = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True, timeout=40)
        returncode = proc.returncode

        new_logs = []
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(init_size)
                    new_logs = [l.strip() for l in f.readlines() if l.strip()]
            except Exception:
                pass

        # 智能提取关键日志中的提示或错误原因
        failure_reason = ""
        for nl in new_logs:
            if any(k in nl for k in ["[错误]", "[-]"]):
                failure_reason = nl
                break
        if not failure_reason:
            for nl in new_logs:
                if any(k in nl for k in ["[提示]", "[尚未开放]", "[时段已截止]", "[今日完成]"]):
                    failure_reason = nl
                    break

        success = (returncode == 0)
        summary = "定时任务仿真触发测试执行成功！" if success else f"仿真执行完成但退出码异常: {returncode}"

        return {
            "success": success,
            "returncode": returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "new_logs": new_logs,
            "failure_reason": failure_reason,
            "summary": summary
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "测试执行超时 (40秒)",
            "new_logs": [],
            "summary": "测试执行超时，请检查网络连接或图片处理逻辑。"
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "new_logs": [],
            "summary": f"执行测试脚本异常: {e}"
        }
