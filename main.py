"""
学搭子自动打卡助手(v1.0)主程序 (main.py)
作者: @护盾电池
项目仓库: https://github.com/Peeeeterr/kassing_signin

一键全自动执行：
  1. 首次运行可通过 -init 命令完成环境与底图初始化向导；
  2. 运行后默认进行 10 秒缓冲倒计时 (支持 Ctrl+C 取消，或通过 -y 跳过)；
  3. 自动从 .env 登录账号并匹配当前开放时段；
  4. 动态生成符合安全半径的随机极坐标定位；
  5. 从 PhotoStorage/ 依据冷却期调度抽取照片并自适应合成防伪水印；
  6. 上传照片并提交官方打卡接口。
"""

import sys
import os
import time
import shutil
import argparse
from datetime import datetime

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

def run_init_wizard():
    """首次运行初始化配置向导"""
    print("=" * 68)
    print("      学搭子 (kassing-signin) v1.0 - 初始化配置向导")
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
        account = input("请输入学搭子登录用户名 (学号或工号): ").strip()
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
        cooldown_input = input("请输入冷却池数量 (最低为 9，回车默认: 9): ").strip()
        if not cooldown_input:
            cooldown_count = 9
            break
        try:
            val = int(cooldown_input)
            if val < 9:
                print(f"[错误] 冷却池数量不能低于 9 次 (当前输入: {val})，请重新输入。")
                continue
            cooldown_count = val
            break
        except ValueError:
            print("[错误] 请输入有效的整数数字。")

    min_required_photos = cooldown_count + 8

    # 4. 拷贝底图并校验
    print("\n" + "-" * 68)
    print("【准备打卡底图】")
    print(f"请将至少 {min_required_photos} 张照片放入 PhotoStorage/ 目录（规则: 冷却池 {cooldown_count} + 8 张）。")
    print(f"目标路径: {PHOTOSTORAGE_DIR}")
    print("防风控建议:")
    print("1. 尽量在不同地点、不同光线、不同衣着下拍照，避免特征过于相似；")
    print("2. 尽量避免包含窗外日光或室外白天光线，防止晚自习下课（夜间）打卡时背景天还大亮。")
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
    print("【其他运行参数】(已内置推荐默认值，直接回车即可)")
    print("-" * 68)

    while True:
        dist_input = input("随机定位半径 (米，建议 10 ~ 150) [默认: 50]: ").strip()
        if not dist_input:
            dist_meters = 50.0
            break
        try:
            val = float(dist_input)
            if val <= 0 or val > 150:
                print(f"[错误] 定位半径必须在 0 到 150 米之间 (当前输入: {val})，请重新输入。")
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

# a. 登录用户名 (工号 / 学号)
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
    print("[+] .env 配置文件已成功生成，初始化完成！")
    print(f"保存位置: {env_path}")
    print(f"运行环境: {python_bin}\n")
    print("后续运行方式:")
    print("  - 正常打卡 (带10秒缓冲): python main.py")
    print("  - 立即打卡 (跳过倒计时): python main.py -y")
    print("  - 自动化定时部署: 详见 README.md")
    print("=" * 68)

def run_countdown(seconds: int = 10):
    """10 秒自动启动倒计时，支持用户按 Ctrl+C 中止"""
    print(f"[*] 系统已就绪，将在 {seconds} 秒后自动执行签到打卡流程...")
    print("    [提示] 如需中止，请随时按下 [Ctrl + C] 取消。")
    try:
        for remaining in range(seconds, 0, -1):
            print(f"\r[自动启动倒计时] 还有 {remaining:2d} 秒自动开始打卡... ", end="", flush=True)
            time.sleep(1)
        print("\r[自动启动倒计时] 倒计时结束，正在启动打卡任务！          \n")
    except KeyboardInterrupt:
        print("\n\n[-] 操作已由用户手动取消，已安全退出。")
        sys.exit(0)

def perform_signin(slot_keyword: str = None, dry_run: bool = False, force: bool = False) -> bool:
    """核心打卡执行全流程"""
    print("=" * 68)
    print("        学搭子 (kassing-signin) v1.0 - 自动化智能打卡流程        ")
    print("=" * 68)
    
    api = KassingAPI()
    
    # 1. 登录
    print("[1/5] 正在登录学搭子账号...")
    api.login(DEFAULT_ACCOUNT, DEFAULT_PASSWORD)
    user_name = api.user_profile.get("name", "")
    
    # 2. 查询时段
    print("[2/5] 正在拉取今日打卡时段...")
    slots = api.get_today_slots()
    if not slots:
        print("[-] 今日未配置任何打卡任务，无需打卡。")
        return True
        
    now_dt = get_beijing_now()
    now_str = now_dt.strftime("%H:%M")
    print(f"      当前北京时间: {now_str} (东八区)")
    
    target_slot = None
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
                    print(f"   [{idx}] {s.get('name')}: [已打卡] ({st} · {signed_time})")
                return True
                
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
    
    print(f"      [+] 目标时段: 【{slot_name}】 (ID: {slot_id})")
    print(f"      [+] 开放时间: {start_time} ~ {end_time}")
    
    # 校验是否已打卡
    if is_signed and not force:
        rec = target_slot.get("myRecord") or {}
        signed_time = format_iso_to_cst(rec.get("signedAt", ""))
        st = format_record_status(rec.get("status", "normal"))
        print(f"\n[提示] 时段【{slot_name}】今日已于 {signed_time} ({st}) 完成打卡。")
        print("    为避免被风控异常检测，已自动停止重复提交 (如需强制打卡请传入 --force)。")
        return True
        
    # 校验是否在开放时间内
    if now_str < start_time and not force:
        print(f"\n[尚未开放] 当前时间 ({now_str}) 尚未到达开放起始时间 ({start_time})。")
        print(f"    建议在 {start_time} ~ {end_time} 期间再次运行本程序。")
        return False
        
    if now_str > end_time and not force:
        print(f"\n[时段已截止] 当前时间 ({now_str}) 已超过截止时间 ({end_time})。")
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
    print(f"      [+] 匹配打卡地点: {loc_name} (基准: {hq_lat}, {hq_lng})")
    print(f"      [+] 动态随机定位: ({rand_lat}, {rand_lng}) | 精度 {rand_acc}m | 距基准点 {actual_dist}m (上限 {DISTANCE_RANGE_METERS}m)")
    
    # 4. 照片选取与水印合成
    print("[3/5] 正在从 PhotoStorage/ 随机抽取照片并生成真实水印...")
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
        print(f"   [打卡人员] {user_name} (学号/工号: {DEFAULT_ACCOUNT})")
        print(f"   [打卡时间] {now_dt.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
        print(f"   [提交坐标] ({rand_lat}, {rand_lng}) [距{loc_name}中心 {actual_dist}m]")
        print(f"   [水印底图] Archives/{os.path.basename(output_photo)}")
        print(f"   [响应数据] {res}")
        print("=" * 68)
        return True
    except Exception as e:
        print(f"[-] 提交打卡记录失败: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="学搭子 (kassing.cn) 自动化智能打卡主程序 (v1.0) | 作者: @护盾电池",
        epilog="""使用示例:
  python main.py -init           运行环境初始化向导 (.env 凭据配置与底图池初始化)
  python main.py                 默认打卡流程 (带 10 秒缓冲倒计时)
  python main.py -y              跳过倒计时立即发起打卡
  python main.py --dry-run       演练模式 (执行完整计算与图片上传，不写入打卡记录)
  python main.py --force         强制打卡模式 (即使不在开放时段内或今日已打卡仍强制提交)
  python main.py --slot 晚自习    指定匹配包含指定关键字的打卡时段
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--init", "-init", action="store_true", help="运行环境初始化向导 (.env 配置与底图检查)")
    parser.add_argument("--no-wait", "-y", action="store_true", help="跳过启动前的 10 秒安全倒计时，直接执行打卡")
    parser.add_argument("--dry-run", action="store_true", help="演练模式 (全流程执行但不真正写入服务器打卡记录)")
    parser.add_argument("--force", action="store_true", help="强制打卡 (即使当前时段未到开放时间或已打过卡仍强制提交)")
    parser.add_argument("--slot", default=None, help="指定打卡时段名称关键字 (如: 晚自习开始 / 晚自习结束)")
    
    args = parser.parse_args()

    # 1. 响应 -init / --init 初始化向导
    if args.init:
        try:
            run_init_wizard()
        except (KeyboardInterrupt, EOFError):
            print("\n\n[-] 操作已取消，向导安全退出。")
        return

    # 2. 前置检查: .env 配置文件存在性及参数有效性校验
    is_valid, errors = validate_env_config()
    if not is_valid:
        print("[错误] 环境配置检查未通过:")
        for err in errors:
            print(f"  - {err}")
        print("\n请先在命令行运行初始化向导进行配置:")
        print("    python main.py -init")
        sys.exit(1)

    # 4. 前置检查: 照片池数量校验 (必须达到 冷却池 + 8 张)
    total_photos = count_input_photos()
    min_required = get_min_photo_pool_size(PHOTO_COOLDOWN_COUNT)
    if total_photos < min_required:
        print("[错误] 照片池底图数量不足，程序拒绝运行。")
        print(f"当前设定照片冷却池为 {PHOTO_COOLDOWN_COUNT} 张（系统最低要求 9 张），总照片数量必须达到 冷却池 + 8 = {min_required} 张。")
        print(f"当前 PhotoStorage/ 目录下仅检测到 {total_photos} 张有效照片。")
        print(f"为了防范平台机械重复审查风险，请往 PhotoStorage/ 目录上传更多不同场景下的打卡照片（至少还需补充 {min_required - total_photos} 张）后再运行。")
        sys.exit(1)

    # 5. 执行 10 秒倒计时 (除非显式指定 --no-wait 或 -y)
    if not args.no_wait:
        run_countdown(10)
        
    perform_signin(slot_keyword=args.slot, dry_run=args.dry_run, force=args.force)

if __name__ == "__main__":
    main()
