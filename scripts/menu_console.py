"""
【测试控制台主入口】(scripts/menu_console.py)
用于集中管理与一键启动各项测试、校验与模拟演练工具：
1. 查看今日签到状态与照片池健康度 (check_status)
2. 测试本地图片生成防伪水印与 EXIF 朝向校正 (test_watermark)
3. 演练打卡全流程 (dry_run_signin，只上传图片不落库)
"""

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def print_menu():
    print("\n" + "=" * 56)
    print("        学搭子 (kassing.cn) - 功能测试与演练控制台        ")
    print("=" * 56)
    print("  [1] 查看今日签到状态与照片池健康度 (Check Status)")
    print("  [2] 测试本地图片生成防伪水印 (Watermark Test)")
    print("  [3] 演练打卡全流程 (Dry Run 保护模式，不落库)")
    print("  [0] 退出测试")
    print("=" * 56)

def main():
    while True:
        print_menu()
        choice = input("请输入测试操作编号 (0-3): ").strip()
        if choice == "1":
            from scripts import check_status
            check_status.main()
        elif choice == "2":
            from scripts import test_watermark
            test_watermark.main()
        elif choice == "3":
            from scripts import dry_run_signin
            dry_run_signin.main()
        elif choice == "0":
            print("[*] 已退出测试控制台。")
            break
        else:
            print("[-] 无效输入，请输入 0、1、2 或 3。")

if __name__ == "__main__":
    main()
