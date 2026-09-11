"""
【PyCharm 运行脚本 2】独立测试图片水印生成
从 PhotoStorage/ 文件夹中随机选择一张底图，打上水印并自动归档至 Archives/ 文件夹。
在 PyCharm 中右键 -> Run 'test_watermark' 即可直接运行。
"""

import sys
import os
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from kassing_signin.config import get_random_input_image, get_output_image_path, ARCHIVES_DIR, OUTPUTS_DIR
from kassing_signin.watermark import apply_watermark, format_watermark_text

# ==================== 测试配置 ====================
USER_NAME = ""           # 水印显示的姓名 (可留空或自定义)
SLOT_NAME = "常规打卡"   # 水印显示的时段名称
# =================================================

def main():
    print("=" * 65)
    print("            学搭子 - 图片水印生成与归档测试            ")
    print("=" * 65)
    
    # 1. 从 PhotoStorage 文件夹中随机选取底图
    try:
        input_image = get_random_input_image()
    except FileNotFoundError as e:
        print(f"[-] 错误: {e}")
        return
        
    # 2. 生成 Archives 归档路径
    output_image = get_output_image_path(slot_name=SLOT_NAME)
    
    # 3. 水印文字格式化
    wm_text = format_watermark_text(user_name=USER_NAME, slot_name=SLOT_NAME)
    
    print(f"[*] 随机选中底图: PhotoStorage/{os.path.basename(input_image)}")
    print(f"[*] 水印文字内容: {wm_text}")
    print(f"[*] 归档输出路径: Archives/{os.path.basename(output_image)}")
    
    # 4. 执行水印渲染与保存
    apply_watermark(input_image, wm_text, output_path=output_image)
    
    # 额外保留一份 last_watermarked.jpg 便于快捷查看
    latest_path = os.path.join(ARCHIVES_DIR, "last_watermarked.jpg")
    shutil.copy2(output_image, latest_path)
    
    print("\n[+] 水印合成并归档完毕！")
    print(f"    - 最新归档文件: Archives/{os.path.basename(output_image)}")
    print(f"    - 快速预览路径: Archives/last_watermarked.jpg")

if __name__ == "__main__":
    main()
