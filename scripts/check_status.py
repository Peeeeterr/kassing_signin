"""
【PyCharm 运行脚本 1】查看今日签到状态与配置
在 PyCharm 中右键 -> Run 'check_status' 即可直接运行。
自动从 .env 读取账号密码，并全面校验定位参数与照片池防重复指标。
"""

import sys
import os
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from kassing_signin.config import (
    get_beijing_now, format_iso_to_cst, format_record_status,
    DEFAULT_ACCOUNT, DEFAULT_PASSWORD, DISTANCE_RANGE_METERS,
    PHOTO_COOLDOWN_COUNT, get_min_photo_pool_size, count_input_photos,
    HQ_LATITUDE, HQ_LONGITUDE, get_random_location, PHOTOSTORAGE_DIR
)
from kassing_signin.kassing_api import KassingAPI

def main():
    print("=" * 68)
    print("            学搭子 - 签到状态与防重复指标检查            ")
    print("=" * 68)
    
    print(f"[*] 账号与定位配置:")
    print(f"    - 账号: {DEFAULT_ACCOUNT}")
    print(f"    - 密码: {'*' * len(DEFAULT_PASSWORD)}")
    print(f"    - 随机定位半径: {DISTANCE_RANGE_METERS} 米，总部基准点: {HQ_LATITUDE}, {HQ_LONGITUDE}")
    r_lat, r_lng, r_acc, r_dist = get_random_location()
    print(f"    - 随机定位试算: 坐标 ({r_lat}, {r_lng})，精度 {r_acc}m，距总部 {r_dist}m")
    
    # 照片池与冷却机制统计
    total_photos = count_input_photos()
    min_required = get_min_photo_pool_size()
    
    print(f"\n[*] 照片池健康度与冷却门槛:")
    print(f"    - PhotoStorage/ 当前底图总数: {total_photos} 张")
    print(f"    - 设定冷却期: {PHOTO_COOLDOWN_COUNT} 次")
    print(f"    - 规则最低容量门槛: {min_required} 张")
    
    if total_photos >= min_required:
        print(f"    - 健康度检查: [合格]，当前 {total_photos} 张 >= 最低要求 {min_required} 张")
    else:
        print(f"    - 健康度检查: [不合格] 需再补充 {min_required - total_photos} 张照片以满足防重复安全标准")
        
    print("-" * 68)
    
    api = KassingAPI()
    api.login(DEFAULT_ACCOUNT, DEFAULT_PASSWORD)
    
    slots = api.get_today_slots()
    if not slots:
        print("[-] 今日未检测到任何打卡任务。")
        return
        
    now_str = get_beijing_now().strftime("%H:%M")
    print(f"\n当前本地系统时间: {now_str}")
    print(f"检测到今日共有 {len(slots)} 个打卡时段：\n")
    
    for idx, s in enumerate(slots, 1):
        slot_id = s.get("slotId")
        name = s.get("name", "未命名")
        start = s.get("startTime", "--:--")
        end = s.get("endTime", "--:--")
        require_photo = s.get("requirePhoto", False)
        signed = s.get("signed", False)
        my_record = s.get("myRecord")
        
        if signed and my_record:
            st = format_record_status(my_record.get("status", "normal"))
            time_st = format_iso_to_cst(my_record.get("signedAt", ""))
            status_text = f"[已打卡] {st} · {time_st}"
        elif now_str < start:
            status_text = f"[未开始] 开放时段: {start} 至 {end}"
        elif now_str > end:
            status_text = f"[已截止] 开放时段: {start} 至 {end}"
        else:
            status_text = f"[当前开放中] 有效至: {end}"
            
        print(f"[{idx}] {name} | ID: {slot_id}")
        print(f"    - 开放时段: {start} ~ {end}")
        print(f"    - 签到状态: {status_text}")
        print(f"    - 拍照规则: {'需要拍照且带水印' if require_photo else '免拍照'}")
        
        candidates = s.get("candidateLocations", [])
        for c in candidates:
            print(f"    - 允许地点: {c.get('name')}，基准坐标: {c.get('latitude')}, {c.get('longitude')}，允许半径: {c.get('radius')}米")
        print("-" * 68)

if __name__ == "__main__":
    main()
