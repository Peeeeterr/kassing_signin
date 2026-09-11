"""
学搭子自动打卡助手(v1.2.0)主程序 (main.py)
作者: @护盾电池
项目仓库: https://github.com/Peeeeterr/kassing_signin

一键全自动执行：
  1. 首次运行可通过 -init 命令完成环境与底图初始化向导；
  2. 支持 -pause / -resume / -status 快捷控制与检测定时打卡状态；
  3. 运行后默认进行 10 秒缓冲倒计时 (支持 Ctrl+C 取消，或通过 -y 跳过)；
  4. 自动从 .env 登录账号并匹配当前开放时段；
  5. 动态生成符合安全半径的随机极坐标定位；
  6. 从 PhotoStorage/ 依据冷却期调度抽取照片并自适应合成防伪水印；
  7. 上传照片并提交官方打卡接口。
"""

import sys
import os
import time
import shutil
import argparse
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from kassing_signin.config import (
    get_beijing_now, format_iso_to_cst, format_record_status,
    DEFAULT_ACCOUNT, DEFAULT_PASSWORD, DISTANCE_RANGE_METERS,
    PHOTO_COOLDOWN_COUNT, count_input_photos, get_min_photo_pool_size,
    validate_env_config,
    get_random_input_image, get_output_image_path, get_random_location,
    ARCHIVES_DIR, PHOTOSTORAGE_DIR, OUTPUTS_DIR, PHOTOSTORE_DIR, INPUTS_DIR, PHOTO_HISTORY_FILE
)
from kassing_signin.kassing_api import KassingAPI
from kassing_signin.watermark import apply_watermark, format_watermark_text
from kassing_signin.scheduler import (
    install_system_schedule, uninstall_system_schedule,
    get_system_schedule_info, compute_recommended_schedules,
    parse_time_hh_mm, check_daemon_status, diagnose_timer_system,
    test_timer_execution, get_skip_count, set_skip_count,
    cancel_skip, consume_skip
)

PAUSE_FILE = os.path.join(PROJECT_ROOT, ".pause")
SKIP_FILE = os.path.join(PROJECT_ROOT, ".skip")

def run_init_wizard():
    """首次运行初始化配置向导"""
    print("=" * 68)
    print("      学搭子 (kassing-signin) v1.2.0 - 初始化配置向导")
    print("=" * 68)

    # 0. 还原初始状态，清除原用户使用痕迹
    print("[*] 正在重置环境并清理历史痕迹...")
    
    # a. 清除照片冷却历史
    for hf in [
        PHOTO_HISTORY_FILE,
        os.path.join(PROJECT_ROOT, "PhotoStorage", ".photo_history.json"),
        os.path.join(PROJECT_ROOT, "PhotoStore", ".photo_history.json"),
        os.path.join(PROJECT_ROOT, "inputs", ".photo_history.json"),
        os.path.join(PROJECT_ROOT, ".photo_history.json")
    ]:
        if os.path.exists(hf):
            try:
                os.remove(hf)
            except Exception:
                pass

    # b. 清除 Archives/ 目录中生成的历史水印图片
    for out_d in [ARCHIVES_DIR, os.path.join(PROJECT_ROOT, "outputs")]:
        if os.path.exists(out_d):
            for fname in os.listdir(out_d):
                if fname != ".gitkeep":
                    fpath = os.path.join(out_d, fname)
                    if os.path.isfile(fpath):
                        try:
                            os.remove(fpath)
                        except Exception:
                            pass

    # c. 清除 logs/ 目录中的运行日志
    logs_dir = os.path.join(PROJECT_ROOT, "logs")
    if os.path.exists(logs_dir):
        for fname in os.listdir(logs_dir):
            if fname != ".gitkeep":
                fpath = os.path.join(logs_dir, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass

    # d. 清除调休暂停标记 .pause
    pause_file = os.path.join(PROJECT_ROOT, ".pause")
    if os.path.exists(pause_file):
        try:
            os.remove(pause_file)
        except Exception:
            pass

    # e. 检查 PhotoStorage/ 是否存在原用户的历史照片
    existing_photos = [
        f for f in os.listdir(PHOTOSTORAGE_DIR)
        if not f.startswith(".") and os.path.isfile(os.path.join(PHOTOSTORAGE_DIR, f))
    ] if os.path.exists(PHOTOSTORAGE_DIR) else []

    if existing_photos:
        clean_ans = input(f"[提示] 检测到 PhotoStorage/ 中存在 {len(existing_photos)} 张原有底图，是否清空？[Y/n]: ").strip().lower()
        if clean_ans in ("", "y", "yes"):
            for f in existing_photos:
                try:
                    os.remove(os.path.join(PHOTOSTORAGE_DIR, f))
                except Exception:
                    pass
            print("[清理] 已清空 PhotoStorage/ 中的历史底图。")
        else:
            print("[保留] 已保留 PhotoStorage/ 中的现有底图。")

    print("[+] 环境重置完成。\n")

    # 1. 账号输入
    while True:
        account = input("请输入学搭子登录用户名: ").strip()
        if account:
            break
        print("[提示] 登录用户名不能为空，请重新输入。")

    # 2. 密码输入
    while True:
        password = input("请输入学搭子登录密码: ").strip()
        if password:
            break
        print("[提示] 登录密码不能为空，请重新输入。")

    # 3. 冷却池说明与输入
    print("\n" + "-" * 68)
    print("【照片冷却池说明】")
    print("每次打卡抽取的照片将冻结 N 次（最低为 9，覆盖 3 天 9 次打卡），防范重复照片审查。")
    print("底图总数须达到「冷却池 + 8 张」，确保轮转池充足。")
    print("-" * 68)

    while True:
        cooldown_input = input("请输入冷却池数量 [最低为 9，默认 9]: ").strip()
        if not cooldown_input:
            cooldown_count = 9
            break
        try:
            val = int(cooldown_input)
            if val < 9:
                print(f"[错误] 冷却池数量不能低于 9 次，当前输入: {val}，请重新输入。")
                continue
            cooldown_count = val
            break
        except ValueError:
            print("[错误] 请输入有效的整数数字。")

    min_required_photos = cooldown_count + 8

    # 4. 拷贝底图并校验
    print("\n" + "-" * 68)
    print("【准备打卡底图】")
    print(f"请将至少 {min_required_photos} 张照片放入 PhotoStorage/ 目录，规则: 冷却池 {cooldown_count} + 8 张。")
    print(f"目标路径: {PHOTOSTORAGE_DIR}")
    print("防风控建议:")
    print("1. 尽量在不同地点、不同光线、不同衣着下拍照，避免特征过于相似；")
    print("2. 尽量避免包含窗外日光或室外白天光线，防止晚自习下课夜间打卡时背景天还大亮。")
    print("支持 jpg/jpeg/png，系统将自动校正朝向与压制防伪水印。")
    print("-" * 68)

    while True:
        confirm = input("放入照片后按回车继续: ").strip().lower()
        if confirm in ("", "y", "yes"):
            cnt = count_input_photos()
            if cnt < min_required_photos:
                print(f"[提示] 当前仅检测到 {cnt} 张有效照片，还需补充至少 {min_required_photos - cnt} 张。")
                continue
            else:
                print(f"[+] 检测到 PhotoStorage/ 已有 {cnt} 张有效照片，校验通过。")
                break

    # 5. 打卡范围等其他参数 (带默认值)
    print("\n" + "-" * 68)
    print("【其他运行参数】")
    print("-" * 68)

    while True:
        dist_input = input("随机定位半径 [米，建议 10 ~ 150，默认 50]: ").strip()
        if not dist_input:
            dist_meters = 50.0
            break
        try:
            val = float(dist_input)
            if val <= 0 or val > 150:
                print(f"[错误] 定位半径必须在 0 到 150 米之间，当前输入: {val}，请重新输入。")
                continue
            dist_meters = val
            break
        except ValueError:
            print("[错误] 请输入有效的数字。")

    # 定时任务调用的 Python 解释器路径 (默认锁定当前运行的虚拟环境/Conda)
    current_python = sys.executable
    py_input = input(f"定时任务 Python 路径 [默认当前环境: {current_python}]: ").strip()
    python_bin = py_input if py_input else current_python

    # 6. 生成并保存 .env
    env_content = f"""# ==============================================================================
# 学搭子 (kassing.cn) 智能打卡配置文件 (.env)
# ==============================================================================

# a. 登录用户名
ACCOUNT={account}

# b. 登录密码
PASSWORD={password}

# c. 距离总部的随机距离范围 (单位: 米)
#    定位坐标将在以总部为中心、该数值为半径的圆形区域内极坐标均匀随机分布。
#    总部打卡允许有效半径为 300 米，建议设置在 20 ~ 150 米之间。
DISTANCE_RANGE_METERS={dist_meters}

# d. 照片冷却期次数 (单位: 次，系统规定最低为 9 次)
#    锁定 3 天打卡 (每天 3 次 × 3 天 = 9 次)，每次抽中后进入冷却期，规避短周期机械复用。
#    系统要求底图库总照片数必须达到: 冷却池 + 8 张 (当前至少需要 {min_required_photos} 张)。
PHOTO_COOLDOWN_COUNT={cooldown_count}

# e. 上传图片最大文件体积限制 (单位: KB，默认 1024 即 1MB)
MAX_PHOTO_SIZE_KB=1024

# f. 定时任务执行时调用的 Python 解释器绝对路径 (锁定当前虚拟环境/Conda)
PYTHON_BIN={python_bin}

# ==============================================================================
# 系统高级参数 (通常保持默认即可)
# ==============================================================================
HQ_LATITUDE=34.802958
HQ_LONGITUDE=113.544171
ACCURACY_MIN=35
ACCURACY_MAX=65
BASE_URL=https://www.kassing.cn
"""

    env_path = os.path.join(PROJECT_ROOT, ".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)

    print("\n" + "=" * 68)
    print("[+] .env 配置文件已成功生成！")
    print(f"保存位置: {env_path}")
    print(f"运行环境: {python_bin}")
    print("=" * 68)

    # 7. 引导一键配置系统定时打卡
    print("\n" + "-" * 68)
    print("【系统定时打卡自动化配置】")
    print("支持自动向操作系统注册后台静默打卡任务。")
    print("-" * 68)
    ask_cron = input("是否现在一键配置系统定时自动打卡？[Y/n]: ").strip().lower()
    if ask_cron not in ["n", "no"]:
        setup_cron_interactive(account=account, password=password)
    else:
        print("\n[*] 已跳过定时任务配置。后续若需开启，可在控制台菜单选择 [6] 随时配置。")

    # 8. 演练测试运行校验 (可选)
    print("\n" + "-" * 68)
    print("【功能测试与演练运行】[可选]")
    print("支持在不向服务器写入真实记录的前提下，全流程测试打卡与防伪逻辑：")
    print("  - 账号登录鉴权与个人信息核对")
    print("  - 时段匹配与随机定位坐标试算")
    print("  - 底图抽取、EXIF 朝向校正与防伪水印合成")
    print("  - 模拟照片上传，演练保护生效，不落库打卡记录")
    print("-" * 68)
    ask_test = input("是否立即执行一次演练测试运行？[y/N]: ").strip().lower()
    if ask_test in ["y", "yes"]:
        print("\n[*] 正在启动演练测试流程...")
        try:
            test_api = KassingAPI()
            test_api.login(account, password)
            perform_signin(dry_run=True, force=True, api=test_api)
        except Exception as e:
            print(f"[-] 演练测试执行异常: {e}")
    else:
        print("\n[*] 已跳过演练测试。")

    print("\n" + "=" * 68)
    print("向导已全部完成！日常使用非常简单，直接启动控制台即可：")
    print("  - Linux / macOS 用户: 在终端运行 ./run.sh")
    print("  - Windows 用户:       直接双击运行 run.bat 启动")
    print("进入控制台后，直接输入数字编号即可直观操作。")
    print("\n测试版快捷测试命令:")
    print("  - 演练打卡全流程: ./run.sh --dry-run (Windows: run.bat --dry-run)")
    print("  - 测试水印生成:   python scripts/test_watermark.py")
    print("  - 诊断图库与状态: python scripts/check_status.py")
    print("  - 综合测试控制台: python scripts/menu_console.py")
    print("=" * 68)

def run_countdown(seconds: int = 10):
    """10 秒自动启动倒计时，支持用户按 Ctrl+C 中止"""
    print(f"[*] 用户身份与打卡任务确认无误，将在 {seconds} 秒后自动执行签到打卡流程...")
    print("    [提示] 如需中止，请随时按下 [Ctrl + C] 取消。")
    try:
        for remaining in range(seconds, 0, -1):
            print(f"\r[自动启动倒计时] 还有 {remaining:2d} 秒自动开始打卡... ", end="", flush=True)
            time.sleep(1)
        print("\r[自动启动倒计时] 倒计时结束，正在启动打卡任务！          \n")
    except KeyboardInterrupt:
        print("\n\n[-] 操作已由用户手动取消，已安全退出。")
        sys.exit(0)

def precheck_and_confirm_user(
    slot_keyword: Optional[str] = None,
    force: bool = False
) -> Tuple[Optional[KassingAPI], Optional[Dict[str, Any]]]:
    """
    打卡前置鉴权、用户信息确认与打卡时段检测
    在进入倒计时或直接打卡前，首先登录验证、确认人员信息与打卡时段。
    若校验不通过或无需打卡，返回 (None, None)。
    """
    print("=" * 68)
    print("                 学搭子 - 打卡前置鉴权与信息确认                 ")
    print("=" * 68)
    print("[*] 正在连接服务器并验证账号凭据...")
    api = KassingAPI()
    try:
        api.login(DEFAULT_ACCOUNT, DEFAULT_PASSWORD)
    except Exception as e:
        print(f"\n[错误] 账号登录鉴权失败: {e}")
        print("    请检查 .env 中的 ACCOUNT 与 PASSWORD 配置，或检查网络连接。")
        return None, None

    user_name = api.user_profile.get("name") or DEFAULT_ACCOUNT
    user_no = api.user_profile.get("no") or DEFAULT_ACCOUNT
    phone = str(api.user_profile.get("phone") or "").strip()
    phone_display = f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else (phone or "")
    dept = (
        api.user_profile.get("deptName")
        or api.user_profile.get("orgName")
        or api.user_profile.get("department")
        or api.user_profile.get("className")
        or ""
    )

    print("\n[+] 用户身份确认:")
    print(f"    - 打卡人员: {user_name} | 用户名: {user_no}")
    if dept:
        print(f"    - 所属组织: {dept}")
    if phone_display:
        print(f"    - 绑定手机: {phone_display}")

    print("\n[*] 正在检测今日打卡时段与任务状态...")
    try:
        slots = api.get_today_slots()
    except Exception as e:
        print(f"[-] 获取今日打卡时段失败: {e}")
        return None, None

    if not slots:
        print("[-] 今日未配置任何打卡任务，无需打卡。")
        return None, None

    now_dt = get_beijing_now()
    now_str = now_dt.strftime("%H:%M")
    print(f"    - 当前北京时间: {now_str}")

    target_slot = None
    if slot_keyword:
        for s in slots:
            if slot_keyword in s.get("name", ""):
                target_slot = s
                break
        if not target_slot:
            print(f"[-] 错误: 未找到名称包含 '{slot_keyword}' 的打卡时段。")
            return None, None
    else:
        # 策略 A: 优先寻找当前处于开放中且未打卡的时段
        for s in slots:
            st = s.get("startTime", "")
            et = s.get("endTime", "")
            if st <= now_str <= et and not s.get("signed"):
                target_slot = s
                break
        # 策略 B: 若无开放中时段，检查是否全部已打卡
        if not target_slot:
            unsigned_slots = [s for s in slots if not s.get("signed")]
            if not unsigned_slots:
                print("\n[今日完成] 今日所有打卡时段均已成功完成签到，无需重复打卡。")
                for idx, s in enumerate(slots, 1):
                    rec = s.get("myRecord") or {}
                    signed_time = format_iso_to_cst(rec.get("signedAt", "--"))
                    st = format_record_status(rec.get("status", "normal"))
                    print(f"   [{idx}] {s.get('name')}: [已打卡] {st} · {signed_time}")
                return None, None
            # 策略 C: 存在未打卡时段，检测最近的一个时段
            for s in unsigned_slots:
                st = s.get("startTime", "")
                if now_str < st:
                    target_slot = s
                    break
            if not target_slot:
                target_slot = unsigned_slots[0]

    slot_id = target_slot.get("slotId")
    slot_name = target_slot.get("name", "常规打卡")
    start_time = target_slot.get("startTime", "")
    end_time = target_slot.get("endTime", "")
    is_signed = target_slot.get("signed", False)

    print(f"    - 匹配目标时段: 【{slot_name}】 | ID: {slot_id}")
    print(f"    - 开放时间窗口: {start_time} ~ {end_time}")

    # 校验是否已打卡
    if is_signed and not force:
        rec = target_slot.get("myRecord") or {}
        signed_time = format_iso_to_cst(rec.get("signedAt", ""))
        st = format_record_status(rec.get("status", "normal"))
        print(f"\n[提示] 时段【{slot_name}】今日已于 {signed_time} 完成打卡。")
        print("    为避免被风控异常检测，已自动停止重复提交，如需强制打卡请传入 --force。")
        return None, None

    # 校验是否在开放时间内
    if now_str < start_time and not force:
        print(f"\n[尚未开放] 当前时间 {now_str} 尚未到达开放起始时间 {start_time}。")
        print(f"    建议在 {start_time} ~ {end_time} 期间再次运行本程序。")
        return None, None

    if now_str > end_time and not force:
        print(f"\n[时段已截止] 当前时间 {now_str} 已超过截止时间 {end_time}。")
        print("    如需尝试补签，请增加 --force 参数。")
        return None, None

    print("=" * 68)
    return api, target_slot

def perform_signin(
    slot_keyword: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
    api: Optional[KassingAPI] = None,
    target_slot: Optional[Dict[str, Any]] = None
) -> bool:
    """核心打卡执行全流程"""
    print("=" * 68)
    print("        学搭子 (kassing-signin) v1.2.0 - 自动化智能打卡流程        ")
    print("=" * 68)
    
    # 1. 登录 (已前置鉴权则复用，否则执行登录)
    if not api:
        api = KassingAPI()
        print("[1/5] 正在登录学搭子账号...")
        try:
            api.login(DEFAULT_ACCOUNT, DEFAULT_PASSWORD)
        except Exception as e:
            print(f"[-] 登录失败: {e}")
            return False
    else:
        print("[1/5] 账号鉴权状态: 已通过 (Token 有效)")
        
    user_name = api.user_profile.get("name", DEFAULT_ACCOUNT)
    
    # 2. 查询与确认打卡时段
    now_dt = get_beijing_now()
    now_str = now_dt.strftime("%H:%M")
    
    if not target_slot:
        print("[2/5] 正在拉取今日打卡时段...")
        try:
            slots = api.get_today_slots()
        except Exception as e:
            print(f"[-] 获取打卡时段失败: {e}")
            return False
            
        if not slots:
            print("[-] 今日未配置任何打卡任务，无需打卡。")
            return True
            
        print(f"      当前北京时间: {now_str} (东八区)")
        
        if slot_keyword:
            for s in slots:
                if slot_keyword in s.get("name", ""):
                    target_slot = s
                    break
            if not target_slot:
                print(f"[-] 错误: 未找到名称包含 '{slot_keyword}' 的打卡时段。")
                return False
        else:
            # 策略 A: 优先寻找当前时间处于开放时段且未打卡的时段
            for s in slots:
                st = s.get("startTime", "")
                et = s.get("endTime", "")
                if st <= now_str <= et and not s.get("signed"):
                    target_slot = s
                    break
                    
            # 策略 B: 若当前无开放时段，查看是否全部已打卡
            if not target_slot:
                unsigned_slots = [s for s in slots if not s.get("signed")]
                if not unsigned_slots:
                    print("\n[今日完成] 今日所有打卡时段均已成功完成签到，无需重复打卡。")
                    for idx, s in enumerate(slots, 1):
                        rec = s.get("myRecord") or {}
                        signed_time = format_iso_to_cst(rec.get("signedAt", "--"))
                        st = format_record_status(rec.get("status", "normal"))
                        print(f"   [{idx}] {s.get('name')}: [已打卡] {st} · {signed_time}")
                    return True
                    
                # 策略 C: 存在未打卡时段，检测最近的一个时段
                for s in unsigned_slots:
                    st = s.get("startTime", "")
                    if now_str < st:
                        target_slot = s
                        break
                if not target_slot:
                    target_slot = unsigned_slots[0]
    else:
        print("[2/5] 目标打卡时段: 已就绪")
        print(f"      当前北京时间: {now_str}")
                    
    slot_id = target_slot.get("slotId")
    slot_name = target_slot.get("name", "常规打卡")
    start_time = target_slot.get("startTime", "")
    end_time = target_slot.get("endTime", "")
    is_signed = target_slot.get("signed", False)
    
    print(f"      [+] 目标时段: 【{slot_name}】 | ID: {slot_id}")
    print(f"      [+] 开放时间: {start_time} ~ {end_time}")
    
    # 校验是否已打卡
    if is_signed and not force:
        rec = target_slot.get("myRecord") or {}
        signed_time = format_iso_to_cst(rec.get("signedAt", ""))
        st = format_record_status(rec.get("status", "normal"))
        print(f"\n[提示] 时段【{slot_name}】今日已于 {signed_time} 完成打卡。")
        print("    为避免被风控异常检测，已自动停止重复提交，如需强制打卡请传入 --force。")
        return True
        
    # 校验是否在开放时间内
    if now_str < start_time and not force:
        print(f"\n[尚未开放] 当前时间 {now_str} 尚未到达开放起始时间 {start_time}。")
        print(f"    建议在 {start_time} ~ {end_time} 期间再次运行本程序。")
        return False
        
    if now_str > end_time and not force:
        print(f"\n[时段已截止] 当前时间 {now_str} 已超过截止时间 {end_time}。")
        print("    如需尝试补签，请增加 --force 参数。")
        return False
        
    # 3. 定位计算
    candidates = target_slot.get("candidateLocations", [])
    if not candidates:
        print("[-] 错误: 该打卡时段未配置允许签到地点。")
        return False
    loc = candidates[0]
    loc_id = loc.get("id")
    loc_name = loc.get("name", "总部")
    hq_lat = loc.get("latitude", 34.802958)
    hq_lng = loc.get("longitude", 113.544171)
    
    rand_lat, rand_lng, rand_acc, actual_dist = get_random_location(hq_lat, hq_lng, DISTANCE_RANGE_METERS)
    print(f"      [+] 匹配打卡地点: {loc_name} | 基准: {hq_lat}, {hq_lng}")
    print(f"      [+] 动态随机定位: ({rand_lat}, {rand_lng}) | 精度 {rand_acc}m | 距基准点 {actual_dist}m | 上限 {DISTANCE_RANGE_METERS}m")
    
    # 4. 照片选取与水印合成 (倒计时结束后重新校准最新时间，确保水印秒级精准)
    print("[3/5] 正在从 PhotoStorage/ 随机抽取照片并生成真实水印...")
    now_dt = get_beijing_now()
    try:
        input_photo = get_random_input_image()
    except Exception as e:
        print(f"\n[-] 无法选取底图: {e}")
        return False
        
    output_photo = get_output_image_path(slot_name=slot_name)
    wm_text = format_watermark_text(user_name=user_name, slot_name=slot_name, dt=now_dt)
    
    print(f"      [+] 选中底图: PhotoStorage/{os.path.basename(input_photo)}")
    print(f"      [+] 防伪水印: {wm_text}")
    
    try:
        photo_bytes = apply_watermark(input_photo, wm_text, output_path=output_photo)
    except Exception as e:
        print(f"[-] 水印合成失败: {e}")
        return False
        
    shutil.copy2(output_photo, os.path.join(ARCHIVES_DIR, "last_watermarked.jpg"))
    print(f"      [+] 归档保存: Archives/{os.path.basename(output_photo)}")
    
    # 5. 上传照片
    print("[4/5] 正在上传水印照片至云端对象存储...")
    try:
        photo_url = api.upload_photo(photo_bytes, filename="signin.jpg", biz="signin")
        print(f"      [+] 上传凭证 Key: {photo_url}")
    except Exception as e:
        print(f"[-] 照片上传失败: {e}")
        return False
        
    # 6. 提交打卡
    if dry_run:
        print("\n[演练保护模式 (--dry-run)] 全流程测试成功，已阻断最终写入请求。")
        return True
        
    print("[5/5] 正在向官方服务器提交最终打卡请求...")
    try:
        res = api.submit_record(
            slot_id=slot_id,
            location_id=loc_id,
            photo_url=photo_url,
            latitude=rand_lat,
            longitude=rand_lng,
            accuracy=rand_acc
        )
        print("=" * 68)
        print(f"[打卡成功] 【{slot_name}】已成功完成签到！")
        print(f"   [打卡人员] {user_name} (用户名: {DEFAULT_ACCOUNT})")
        print(f"   [打卡时间] {now_dt.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
        print(f"   [提交坐标] ({rand_lat}, {rand_lng}) [距{loc_name}中心 {actual_dist}m]")
        print(f"   [水印底图] Archives/{os.path.basename(output_photo)}")
        print(f"   [响应数据] {res}")
        print("=" * 68)
        return True
    except Exception as e:
        print(f"[-] 提交打卡记录失败: {e}")
        return False

def pause_cron():
    """快捷暂停定时自动打卡"""
    try:
        with open(PAUSE_FILE, "w", encoding="utf-8") as f:
            f.write(f"Paused at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        print("[+] 自动打卡已成功暂停！")
        print("    已进入放假/调休模式，到达打卡时间将自动跳过。")
        print("    如需恢复自动打卡，可在控制台选择 [5] 一键恢复。")
    except Exception as e:
        print(f"[-] 暂停自动打卡失败: {e}")

def resume_cron():
    """快捷恢复/开启定时自动打卡 (清除暂停与跳过标识)"""
    cleared = []
    if os.path.exists(PAUSE_FILE):
        try:
            os.remove(PAUSE_FILE)
            cleared.append("暂停打卡状态")
        except Exception as e:
            print(f"[-] 清除暂停标识失败: {e}")

    if get_skip_count(PROJECT_ROOT) > 0:
        if cancel_skip(PROJECT_ROOT):
            cleared.append("跳过打卡设置")
        else:
            print("[-] 清除跳过设置失败。")

    if cleared:
        print(f"[+] 自动打卡已恢复正常运行！已解除: {'、'.join(cleared)}")
        print("    已恢复正常调度，到达设定时间后将正常执行自动打卡。")
    else:
        print("[*] 当前自动打卡处于正常运行状态。")
        print("    如需放假/调休暂停打卡，可在控制台选择 [4] 暂停打卡或 [9] 跳过打卡。")

def skip_cron(count: int = 1) -> bool:
    """
    设定跳过后续打卡任务
    :param count: 跳过打卡次数，默认值为 1 (跳过单次打卡)
    """
    if count < 1:
        print("[-] 跳过次数必须大于或等于 1。若需取消跳过，请运行: ./run.sh -cancel-skip 或在控制台按 [5] 恢复。")
        return False

    success = set_skip_count(count, PROJECT_ROOT)
    if success:
        if count == 1:
            print("[+] 已成功设置【跳过单次打卡】！")
            print("    系统将在下一次到达打卡时间时自动安全跳过，之后自动恢复正常打卡。")
        else:
            print(f"[+] 已成功设置【跳过后续 {count} 次打卡】！")
            print(f"    系统将在后续 {count} 次到达打卡时间时自动安全跳过，配额用尽后自动恢复正常。")
        print("    如需提前取消跳过设置，可运行: ./run.sh -cancel-skip，或在控制台按 [5] 恢复")
    else:
        print("[-] 设置跳过打卡失败，请检查文件写入权限。")
    return success

def cancel_skip_cron() -> bool:
    """取消已设定的跳过打卡任务"""
    if get_skip_count(PROJECT_ROOT) > 0:
        if cancel_skip(PROJECT_ROOT):
            print("[+] 已成功取消跳过打卡设置！后续打卡将正常按时执行。")
            return True
        else:
            print("[-] 取消跳过打卡失败。")
            return False
    else:
        print("[*] 当前未设置跳过打卡任务。")
        return True

def skip_cron_interactive():
    """交互式配置跳过打卡次数向导"""
    print("\n" + "=" * 68)
    print("                 设置跳过后续定时打卡                 ")
    print("=" * 68)
    current_skip = get_skip_count(PROJECT_ROOT)
    if current_skip > 0:
        print(f"[*] 当前已生效跳过设置: 剩余 {current_skip} 次打卡")

    print("适用场景: 今日已在手机手动打卡、或临时请假外出。")
    print("执行逻辑: 到达打卡时间后自动跳过并递减计数，配额归零后自动恢复正常打卡。")
    raw = input("\n请输入要跳过的打卡次数 [直接回车默认跳过 1 次]: ").strip()
    if not raw:
        skip_count = 1
    else:
        try:
            skip_count = int(raw)
        except ValueError:
            print("[-] 输入无效，次数必须为正整数。操作已取消。")
            return
    skip_cron(skip_count)

def setup_cron_interactive(api: Optional[KassingAPI] = None, account: Optional[str] = None, password: Optional[str] = None):
    """交互式配置系统定时打卡任务"""
    print("\n" + "=" * 68)
    print("                 系统定时自动打卡配置向导                 ")
    print("=" * 68)
    
    slots = []
    try:
        if not api:
            target_acc = account or DEFAULT_ACCOUNT
            target_pwd = password or DEFAULT_PASSWORD
            if target_acc and target_pwd:
                temp_api = KassingAPI()
                temp_api.login(target_acc, target_pwd)
                slots = temp_api.get_today_slots()
        else:
            slots = api.get_today_slots()
    except Exception as e:
        print(f"[*] 联网获取打卡时段失败，将使用标准时段: {e}")

    schedules = compute_recommended_schedules(slots)
    print("\n检测/推荐的定时打卡时段如下:")
    for idx, item in enumerate(schedules, 1):
        raw_info = f"，系统开放: {item['raw_start']} ~ {item['raw_end']}" if "raw_start" in item and item["raw_start"] else ""
        print(f"  [{idx}] {item['name']}{raw_info} -> 推荐定时: {item['time']}")

    print("\n请选择打卡周期:")
    print("  [1] 仅周一至周五打卡 [推荐]")
    print("  [2] 每天打卡")
    cycle_choice = input("请输入选项编号 [默认 1]: ").strip()
    workday_only = (cycle_choice != "2")

    print(f"\n当前推荐打卡时间点: {', '.join(s['time'] for s in schedules)}")
    custom_times_input = input("如需自定义打卡时间请输入，多个时间用逗号分隔，如 08:05, 18:20, 20:45 [直接回车使用推荐]: ").strip()

    if custom_times_input:
        raw_parts = [p.strip() for p in custom_times_input.replace("，", ",").split(",") if p.strip()]
        valid_custom = []
        for idx, p in enumerate(raw_parts, 1):
            parsed = parse_time_hh_mm(p)
            if parsed:
                valid_custom.append({
                    "name": schedules[idx-1]["name"] if idx <= len(schedules) else f"自定义时段_{idx}",
                    "time": f"{parsed[0]:02d}:{parsed[1]:02d}",
                    "delay": 180
                })
            else:
                print(f"[警告] 忽略不合法的时间格式: {p}，正确格式应为 HH:MM，如 08:30")
        if valid_custom:
            schedules = valid_custom

    print(f"\n[*] 正在向操作系统注册定时打卡任务...")
    ok, msg = install_system_schedule(PROJECT_ROOT, schedules, workday_only=workday_only)
    if ok:
        print(f"[+] {msg}")
        print("    系统定时器将在设定时间自动调度打卡脚本，并记录日志到 logs/cron.log。")
        print("    如需临时暂停，可在控制台选择 [4] 暂停打卡。")
    else:
        print(f"[-] 安装定时任务失败: {msg}")
        print("    您可以后续手动配置系统定时器，参考项目 README.md 说明。")

def remove_cron_interactive():
    """交互式卸载系统定时打卡任务"""
    print("\n" + "=" * 68)
    print("                 系统定时打卡任务卸载                 ")
    print("=" * 68)
    confirm = input("确定要从操作系统中移除本项目的全部定时打卡任务吗？[y/N]: ").strip().lower()
    if confirm in ["y", "yes"]:
        ok, msg = uninstall_system_schedule(PROJECT_ROOT)
        if ok:
            print(f"[+] {msg}")
        else:
            print(f"[-] 卸载失败: {msg}")
    else:
        print("[*] 操作已取消。")

def show_cron_status():
    """查看当前定时自动打卡运行状态与自然语言规则"""
    print("=" * 68)
    print("                    自动打卡运行状态与定时检测                    ")
    print("=" * 68)

    # 1. 守护进程检测
    daemon_info = check_daemon_status()
    daemon_tag = "[正常]" if daemon_info["is_active"] else "[异常]"
    print(f"[*] 系统定时服务: {daemon_tag} {daemon_info['service_name']} - {daemon_info['status_text']}")
    if not daemon_info["is_active"]:
        print(f"    提示: {daemon_info['advice']}")

    # 2. 运行/暂停与跳过状态
    is_paused = os.path.exists(PAUSE_FILE)
    skip_cnt = get_skip_count(PROJECT_ROOT)
    if is_paused:
        pause_mtime = datetime.fromtimestamp(os.path.getmtime(PAUSE_FILE)).strftime('%Y-%m-%d %H:%M:%S')
        print(f"[*] 运行开关状态: 暂停打卡中，自 {pause_mtime} 起暂停")
        print("    说明: 当前处于放假调休模式，到点将自动跳过。恢复打卡请在控制台按 [5]")
    else:
        print("[*] 运行开关状态: 正常启用中")
        print("    说明: 系统将按时自动执行打卡。放假调休请在控制台按 [4] 暂停打卡")

    if skip_cnt > 0:
        print(f"[*] 跳过打卡状态: 生效中，剩余跳过次数: {skip_cnt} 次")
        print("    说明: 到达设定时间将自动跳过并递减计数，归零后恢复正常打卡。")
        print("    提示: 取消跳过请在控制台按 [5] 或运行: ./run.sh -cancel-skip")
    else:
        print("[*] 跳过打卡状态: 未设定")

    # 3. 定时规则与人性化时间解读
    sched_info = get_system_schedule_info()
    if sched_info["is_configured"]:
        print("\n[+] 自动打卡任务设置:")
        if sched_info.get("rules_detail"):
            for r in sched_info["rules_detail"]:
                next_hint = f" | 下次预计: {r['next_run_str']}" if r.get("next_run_str") else ""
                print(f"    - {r['human_desc']}{next_hint}")
        elif sched_info.get("human_rules"):
            for hr in sched_info["human_rules"]:
                print(f"    - {hr}")
        print("    提示: 如需修改打卡时间请在控制台按 [6]，彻底关闭请按 [7]")
    else:
        print("\n[-] 自动打卡设置: 当前尚未配置定时规则")
        print("    提示: 可在控制台选择 [6] 一键开启后台每天定时打卡")

    # 4. 检查最新日志
    log_file = os.path.join(PROJECT_ROOT, "logs", "cron.log")
    if os.path.exists(log_file):
        print("\n[*] 最近执行日志记录: logs/cron.log")
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                last_lines = [line.strip() for line in lines[-5:] if line.strip()]
                if last_lines:
                    for line in last_lines:
                        print(f"    {line}")
                else:
                    print("    暂无日志记录")
        except Exception:
            pass
    else:
        print("\n[*] 尚未产生运行日志文件，首次定时执行后将自动记录")

    print("\n[功能指引] 如需全面测试定时器健康度或仿真触发执行：")
    print("  - 终端运行: python main.py -test-cron，或在控制台按 [13]")
    print("=" * 68)

def run_timer_test(dry_run: bool = True):
    """执行系统定时器全套健康诊断与全链路仿真触发测试"""
    from scripts import test_timer
    test_timer.main()

def show_today_records():
    """查看今日打卡任务与签到记录"""
    print("=" * 68)
    print("                    学搭子今日打卡记录查询                    ")
    print("=" * 68)

    # 1. 检查凭据有效性
    is_valid, errors = validate_env_config()
    if not is_valid:
        print("[错误] 环境配置检查未通过，无法查询记录:")
        for err in errors:
            print(f"  - {err}")
        print("\n请先运行初始化向导进行配置: ./run.sh 或 ./run.sh -init")
        return

    # 2. 登录账号
    try:
        api = KassingAPI()
        api.login(DEFAULT_ACCOUNT, DEFAULT_PASSWORD)
        user_name = api.user_profile.get("name", DEFAULT_ACCOUNT)
        user_no = api.user_profile.get("no", DEFAULT_ACCOUNT)
        print(f"[*] 登录人员: {user_name} | 用户名: {user_no}")
    except Exception as e:
        print(f"[-] 登录失败，无法获取打卡记录: {e}")
        return

    # 3. 查询今日时段
    try:
        slots = api.get_today_slots()
    except Exception as e:
        print(f"[-] 查询今日时段失败: {e}")
        return

    now_dt = get_beijing_now()
    now_str = now_dt.strftime("%H:%M")
    print(f"[*] 当前北京时间: {now_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[*] 今日共有 {len(slots)} 个打卡时段任务:\n")

    if not slots:
        print("    今日暂无开放的打卡任务。")
    else:
        for idx, s in enumerate(slots, 1):
            slot_id = s.get("slotId")
            name = s.get("name", "未命名时段")
            start = s.get("startTime", "--:--")
            end = s.get("endTime", "--:--")
            signed = s.get("signed", False)
            my_record = s.get("myRecord") or {}

            if signed:
                st = format_record_status(my_record.get("status", "normal"))
                signed_time = format_iso_to_cst(my_record.get("signedAt", ""))
                loc_info = my_record.get("locationName", "")
                loc_str = f" [地点: {loc_info}]" if loc_info else ""
                status_desc = f"[已打卡] {st} · {signed_time}{loc_str}"
            elif now_str < start:
                status_desc = f"[未开始] 开放时段: {start} ~ {end}"
            elif now_str > end:
                status_desc = f"[已截止] 开放时段: {start} ~ {end}"
            else:
                status_desc = f"[开放打卡中] 截止时间: {end}"

            print(f"  [{idx}] 【{name}】 | 时段 ID: {slot_id}")
            print(f"      - 开放窗口: {start} ~ {end}")
            print(f"      - 签到状态: {status_desc}")

    # 4. 统计本地生成的水印打卡照片归档
    if os.path.exists(ARCHIVES_DIR):
        photos = [
            f for f in os.listdir(ARCHIVES_DIR)
            if not f.startswith(".") and f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        photos.sort(key=lambda x: os.path.getmtime(os.path.join(ARCHIVES_DIR, x)), reverse=True)
        print("\n[*] 本地近期水印打卡照片归档: Archives/")
        if photos:
            for p in photos[:3]:
                ptime = datetime.fromtimestamp(os.path.getmtime(os.path.join(ARCHIVES_DIR, p))).strftime("%Y-%m-%d %H:%M:%S")
                print(f"    - {p} | 生成时间: {ptime}")
        else:
            print("    暂无生成的打卡照片")

    print("=" * 68)

def main():
    parser = argparse.ArgumentParser(
        description="学搭子 (kassing.cn) 自动化智能打卡主程序 v1.2.0 | 作者: @护盾电池",
        epilog="""使用示例:
  [推荐入口]
  ./run.sh                       Linux/macOS 统一控制台入口
  run.bat                        Windows 统一控制台入口

  [命令行快捷透传]
  ./run.sh -y                    立即打卡
  ./run.sh -records              查询今日打卡时段任务与签到记录
  ./run.sh -status               查看定时任务当前运行状态与日志
  ./run.sh -test-cron            全面体检定时器健康度并进行仿真触发测试
  ./run.sh -skip                 快捷跳过单次打卡
  ./run.sh --skip 3              跳过后续指定次数打卡
  ./run.sh -cancel-skip          取消跳过打卡设置
  ./run.sh -pause                快捷暂停定时自动打卡
  ./run.sh -resume               快捷恢复定时自动打卡
  ./run.sh -setup-cron           一键配置或重新设置系统定时打卡任务
  ./run.sh -remove-cron          一键卸载并彻底清理系统中的定时打卡任务
  ./run.sh --dry-run             演练模式
  ./run.sh --force               强制打卡模式
  ./run.sh --slot 晚自习          指定匹配包含指定关键字的打卡时段
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--init", "-init", action="store_true", help="运行环境初始化向导")
    parser.add_argument("--records", "-records", action="store_true", help="查看今日打卡任务状态与签到记录")
    parser.add_argument("--setup-cron", "-setup-cron", action="store_true", help="一键配置或重新设置系统定时自动打卡任务")
    parser.add_argument("--remove-cron", "-remove-cron", action="store_true", help="一键卸载并彻底清理系统中的定时打卡任务")
    parser.add_argument("--pause", "-pause", action="store_true", help="暂停定时自动打卡")
    parser.add_argument("--resume", "-resume", "--start", "-start", action="store_true", help="恢复/开启定时自动打卡")
    parser.add_argument("--skip", "-skip", nargs="?", const=1, type=int, default=None, help="跳过后续打卡任务，默认跳过 1 次，支持指定次数如: --skip 2")
    parser.add_argument("--cancel-skip", "-cancel-skip", action="store_true", help="取消已设定的跳过打卡设置")
    parser.add_argument("--skip-interactive", action="store_true", help="交互式向导设置跳过打卡次数")
    parser.add_argument("--status", "-status", action="store_true", help="查看定时打卡当前运行状态及定时器配置")
    parser.add_argument("--test-cron", "-test-cron", action="store_true", help="全面诊断系统定时器运行环境并进行全链路仿真触发测试")
    parser.add_argument("--no-wait", "-y", action="store_true", help="跳过启动前的 10 秒安全倒计时，直接执行打卡")
    parser.add_argument("--dry-run", action="store_true", help="演练模式，全流程执行但不真正写入服务器打卡记录")
    parser.add_argument("--force", action="store_true", help="强制打卡，即使当前时段未到开放时间或已打过卡仍强制提交")
    parser.add_argument("--slot", default=None, help="指定打卡时段名称关键字，如: 晚自习开始 / 晚自习结束")
    
    args = parser.parse_args()

    # 1. 响应定时任务管理与状态控制命令
    if args.records:
        show_today_records()
        return

    if args.setup_cron:
        try:
            setup_cron_interactive()
        except (KeyboardInterrupt, EOFError):
            print("\n\n[-] 操作已取消。")
        return

    if args.remove_cron:
        try:
            remove_cron_interactive()
        except (KeyboardInterrupt, EOFError):
            print("\n\n[-] 操作已取消。")
        return

    if args.pause:
        pause_cron()
        return

    if args.resume:
        resume_cron()
        return

    if args.skip is not None:
        skip_cron(args.skip)
        return

    if args.cancel_skip:
        cancel_skip_cron()
        return

    if args.skip_interactive:
        try:
            skip_cron_interactive()
        except (KeyboardInterrupt, EOFError):
            print("\n\n[-] 操作已取消。")
        return

    if args.status:
        show_cron_status()
        return

    if args.test_cron:
        run_timer_test(dry_run=True)
        return

    # 2. 响应 -init / --init 初始化向导
    if args.init:
        try:
            run_init_wizard()
        except (KeyboardInterrupt, EOFError):
            print("\n\n[-] 操作已取消，向导安全退出。")
        return

    # 3. 检查跳过打卡设置 (若命中跳过且非强制打卡，则安全跳过并递减配额)
    skip_cnt = get_skip_count(PROJECT_ROOT)
    if skip_cnt > 0:
        if args.force:
            print(f"[*] 检测到强制打卡参数 (--force)，忽略当前生效中的跳过设置 (当前剩余跳过次数: {skip_cnt} 次)。\n")
        elif args.dry_run:
            print(f"[*] [演练模式] 当前已设定跳过打卡 (剩余: {skip_cnt} 次)。演练保护模式下不消耗跳过配额。\n")
        else:
            consumed, remaining = consume_skip(PROJECT_ROOT)
            print("=" * 68)
            print("[*] 提示: 检测到已设定跳过打卡任务！")
            print("    [+] 本次打卡已成功安全跳过。")
            if remaining > 0:
                print(f"    [*] 剩余跳过次数: {remaining} 次 (后续打卡将继续自动跳过)")
            else:
                print("    [*] 跳过配额已用完，下次到达打卡时间将恢复正常打卡。")
            print("=" * 68)
            sys.exit(0)

    # ==============================================================================
    # 阶段一：本地运行环境与底图池检测 (全本地离线校验)
    # ==============================================================================
    # 1. 配置文件存在性及参数有效性校验
    is_valid, errors = validate_env_config()
    if not is_valid:
        print("[错误] 本地环境配置检查未通过:")
        for err in errors:
            print(f"  - {err}")
        print("\n请先运行初始化向导进行配置:")
        print("    ./run.sh (首次启动将自动引导) 或 ./run.sh -init (Windows: run.bat -init)")
        sys.exit(1)

    # 2. 照片池底图数量校验 (必须达到 冷却池 + 8 张)
    total_photos = count_input_photos()
    min_required = get_min_photo_pool_size(PHOTO_COOLDOWN_COUNT)
    if total_photos < min_required:
        print("[错误] 本地底图数量不足，打卡终止。")
        print(f"当前设定照片冷却池为 {PHOTO_COOLDOWN_COUNT} 张（系统最低要求 9 张），总照片数量必须达到 冷却池 + 8 = {min_required} 张。")
        print(f"当前 PhotoStorage/ 目录下仅检测到 {total_photos} 张有效照片。")
        print(f"为了防范平台机械重复审查风险，请往 PhotoStorage/ 目录上传更多不同场景下的打卡照片（至少还需补充 {min_required - total_photos} 张）后再运行。")
        sys.exit(1)

    # ==============================================================================
    # 阶段二：联网鉴权、用户信息确认与任务时段诊断
    # ==============================================================================
    api, target_slot = precheck_and_confirm_user(slot_keyword=args.slot, force=args.force)
    if not api or not target_slot:
        # 鉴权失败、未开放、已打卡或无任务，前置检测已输出明确提示，安全退出
        sys.exit(0 if (api is not None) else 1)

    # ==============================================================================
    # 阶段三：安全倒计时缓冲与打卡执行
    # ==============================================================================
    # 检查暂停标识
    if os.path.exists(PAUSE_FILE):
        print("[*] 提示: 当前处于暂停自动打卡状态。本次手动打卡不受影响。")
        print("    如需恢复自动打卡，可在控制台选择 [5] 一键恢复。\n")

    # 执行 10 秒倒计时 (除非显式指定 --no-wait 或 -y)
    if not args.no_wait:
        run_countdown(10)
    else:
        print("[*] 检测到跳过倒计时参数 (-y)，立即执行打卡...\n")

    # 提交打卡
    success = perform_signin(
        slot_keyword=args.slot,
        dry_run=args.dry_run,
        force=args.force,
        api=api,
        target_slot=target_slot
    )
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
