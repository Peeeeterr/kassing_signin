"""
【PyCharm 运行脚本 3】演练打卡全流程 (--dry-run 保护模式)
在 PyCharm 中右键 -> Run 'dry_run_signin' 即可直接运行。
1. 自动从 .env 读取账号密码登录；
2. 自动从 PhotoStorage/ 文件夹随机抽取底图；
3. 合成防伪水印并归档到 Archives/ 文件夹；
4. 上传到服务器云存储；
5. 在 .env 指定的距离总部的范围内【随机生成经纬度定位】；
6. 演练保护机制生效，不向服务端写入最终记录。
"""

import sys
import os
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from kassing_signin.config import (
    get_beijing_now,
    DEFAULT_ACCOUNT, DEFAULT_PASSWORD, DISTANCE_RANGE_METERS,
    get_random_input_image, get_output_image_path, get_random_location,
    ARCHIVES_DIR, OUTPUTS_DIR
)
from kassing_signin.kassing_api import KassingAPI
from kassing_signin.watermark import apply_watermark, format_watermark_text

def main():
    print("=" * 65)
    print("          学搭子 (kassing.cn) - 打卡全流程演练 (--dry-run)          ")
    print("=" * 65)
    
    api = KassingAPI()
    
    # 1. 登录
    print("[1/5] 正在登录系统...")
    api.login(DEFAULT_ACCOUNT, DEFAULT_PASSWORD)
    user_name = api.user_profile.get("name", "")
    
    # 2. 查询时段配置
    print("[2/5] 正在拉取今日时段配置...")
    slots = api.get_today_slots()
    if not slots:
        print("[-] 错误: 今日无任何打卡时段")
        return
        
    # 寻找第一个未打卡的时段
    target_slot = None
    for s in slots:
        if not s.get("signed"):
            target_slot = s
            break
    if not target_slot:
        target_slot = slots[0]
        
    slot_id = target_slot.get("slotId")
    slot_name = target_slot.get("name", "晚自习开始")
    print(f"      [+] 目标时段: {slot_name} (ID: {slot_id})")
    print(f"      [+] 开放时间: {target_slot.get('startTime')} ~ {target_slot.get('endTime')}")
    print(f"      [+] 当前打卡状态: {'已打卡' if target_slot.get('signed') else '未打卡'}")
    
    # 匹配地点
    candidates = target_slot.get("candidateLocations", [])
    if not candidates:
        print("[-] 错误: 该时段未配置允许地点")
        return
    loc = candidates[0]
    loc_id = loc.get("id")
    loc_name = loc.get("name", "总部")
    hq_lat = loc.get("latitude", 34.802958)
    hq_lng = loc.get("longitude", 113.544171)
    
    # 3. 随机生成定位坐标
    rand_lat, rand_lng, rand_acc, actual_dist = get_random_location(hq_lat, hq_lng, DISTANCE_RANGE_METERS)
    print(f"      [+] 匹配打卡地点: {loc_name} (ID: {loc_id})")
    print(f"      [+] 动态生成随机定位: ({rand_lat}, {rand_lng}), 精度 {rand_acc}m (距{loc_name}中心 {actual_dist}m / 上限 {DISTANCE_RANGE_METERS}m)")
    
    # 4. 从 PhotoStorage 随机取图，合成水印并归档至 Archives
    print("[3/5] 正在从 PhotoStorage/ 随机抽取照片并添加防伪水印...")
    try:
        input_photo = get_random_input_image()
    except FileNotFoundError as e:
        print(f"[-] {e}")
        return
        
    output_photo = get_output_image_path(slot_name=slot_name)
    wm_text = format_watermark_text(user_name=user_name, slot_name=slot_name)
    
    print(f"      [+] 抽取照片: PhotoStorage/{os.path.basename(input_photo)}")
    print(f"      [+] 水印内容: {wm_text}")
    photo_bytes = apply_watermark(input_photo, wm_text, output_path=output_photo)
    
    # 留存 last_watermarked.jpg
    shutil.copy2(output_photo, os.path.join(ARCHIVES_DIR, "last_watermarked.jpg"))
    print(f"      [+] 归档保存: Archives/{os.path.basename(output_photo)}")
    
    # 5. 上传到云端
    print("[4/5] 正在将水印照片上传至网站对象存储...")
    photo_url = api.upload_photo(photo_bytes, filename="signin.jpg", biz="signin")
    print(f"      [+] 云端存储凭证 photoUrl: {photo_url}")
    
    # 6. 参数预览与安全拦截
    print("[5/5] 拟提交打卡请求参数预览:")
    print("-----------------------------------------------------------------")
    print(f"  POST https://www.kassing.cn/api/signin/regular/record")
    print(f"  Payload:")
    print(f"    - slotId:      \"{slot_id}\"")
    print(f"    - locationId:  \"{loc_id}\"")
    print(f"    - photoUrl:    \"{photo_url}\"")
    print(f"    - latitude:    {rand_lat}  (动态随机)")
    print(f"    - longitude:   {rand_lng}  (动态随机)")
    print(f"    - accuracy:    {rand_acc}  (动态随机)")
    print("-----------------------------------------------------------------")
    print("🛡️ 【演练保护机制生效】本次运行为 --dry-run 演练，未向服务端真正发起写入！")
    print("🎉 照片上传成功，所有参数完全对齐真实打卡协议，待打卡时间开放时即可进行正式打卡。")

if __name__ == "__main__":
    main()
