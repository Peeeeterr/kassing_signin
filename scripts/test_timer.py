"""
【PyCharm 运行脚本 4】系统定时器健康体检与全链路测试
在 PyCharm 中右键 -> Run 'test_timer' 即可直接运行。
针对定时任务未能正常工作的常见原因进行全面诊断：
  1. 系统定时守护进程状态 (Linux cron / Windows Task Scheduler)
  2. 系统时区与东八区北京时间同步状态
  3. 系统已注册定时打卡规则解析与自然语言解读
  4. 脚本可执行权限 (+x) 与 Python 虚拟环境依赖校验
  5. 调休/暂停标记 (.pause) 与防重复签到排查
  6. 全链路仿真触发测试 (立即触发 + dry-run 保护模式)
"""

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from kassing_signin.scheduler import (
    diagnose_timer_system, test_timer_execution, get_system_schedule_info
)

def main():
    print("=" * 68)
    print("            学搭子 - 系统定时器健康诊断与全链路测试            ")
    print("=" * 68)

    diag = diagnose_timer_system(PROJECT_ROOT)

    # 1. 守护进程状态
    daemon = diag["daemon"]
    daemon_flag = "[合格]" if daemon["is_active"] else "[异常]"
    print(f"\n[*] 1. 定时守护进程状态: {daemon_flag}")
    print(f"    - 服务类型: {daemon['service_name']}")
    print(f"    - 当前状态: {daemon['status_text']}")
    if not daemon["is_active"]:
        print(f"    - 修复指引:\n      {daemon['advice']}")

    # 2. 系统时钟与时区比对
    clock = diag["clock"]
    clock_flag = "[合格]" if clock["is_synced"] else "[警告]"
    print(f"\n[*] 2. 系统时钟与北京时间: {clock_flag}")
    print(f"    - 本地系统时钟: {clock['local_time']}")
    print(f"    - 标准北京时间: {clock['cst_time']}")
    print(f"    - 本地时区估算: UTC{clock['tz_offset_hours']:+d}")
    if not clock["is_synced"]:
        print(f"    - 提示说明: {clock['advice']}")

    # 3. 注册的定时规则与自然语言解读
    sched = diag["schedule"]
    sched_flag = "[已配置]" if sched["is_configured"] else "[未配置]"
    print(f"\n[*] 3. 定时打卡规则配置: {sched_flag}")
    print(f"    - 运行平台: {sched['platform']}")
    if sched["is_configured"]:
        print(f"    - 规则总数: {sched['rules_count']} 个任务")
        print(f"    - 默认周期: {sched['cycle_name']}")
        print("    - 详细定时列表:")
        for r in sched["rules_detail"]:
            next_hint = f" | 下次: {r['next_run_str']}" if r.get("next_run_str") else ""
            print(f"      * {r['human_desc']}{next_hint}")
    else:
        print("    - [警告] 尚未在操作系统中注册打卡任务！到达打卡时间将不会自动执行。")
        print("    - 解决办法: 请在控制台选择 [6] 开启/配置定时打卡，或运行 ./run.sh -setup-cron")

    # 4. 关键脚本权限与运行环境
    print(f"\n[*] 4. 关键脚本权限与运行环境:")
    for gp in diag["good_points"]:
        if "脚本权限" in gp or "脚本状态" in gp or "Python" in gp:
            print(f"    - [合格] {gp}")
    for iss in diag["issues"]:
        if "脚本" in iss or "Python" in iss:
            print(f"    - [异常] {iss}")
    for warn in diag["warnings"]:
        if "Python" in warn:
            print(f"    - [警告] {warn}")

    # 5. 暂停/调休/跳过模式检测
    print(f"\n[*] 5. 调休/暂停/跳过状态检测:")
    if diag["is_paused"]:
        print("    - [注意] 当前处于【暂停打卡】状态！")
        print("    - 到达设定打卡时间后将自动跳过，不执行打卡。")
        print("    - 若需恢复自动打卡，请在控制台按 [5] 恢复，或运行: ./run.sh -resume")
    elif diag.get("skip_count", 0) > 0:
        print(f"    - [注意] 当前设定了【跳过打卡】，剩余次数: {diag['skip_count']} 次！")
        print("    - 到达设定打卡时间后将自动跳过并递减计数，归零后恢复正常打卡。")
        print("    - 若需取消跳过，请在控制台按 [5] 恢复，或运行: ./run.sh -cancel-skip")
    else:
        print("    - [正常] 自动打卡正常处于启用状态")

    # 6. 仿真触发执行测试
    print("\n" + "-" * 68)
    print("[*] 6. 发起全链路仿真触发测试...")
    print("    模式: 立即触发 + 演练保护")
    test_res = test_timer_execution(PROJECT_ROOT, dry_run=True)
    if test_res["success"]:
        print(f"[+] 仿真触发测试成功！退出码: 0")
        if test_res["new_logs"]:
            print("    最新写入日志片段: logs/cron.log")
            for nl in test_res["new_logs"][-5:]:
                print(f"      {nl}")
    else:
        print(f"[-] 仿真触发测试未完全通过: {test_res['summary']}")
        if test_res.get("failure_reason"):
            print(f"    核心原因诊断: {test_res['failure_reason']}")
        if test_res["new_logs"]:
            print("    执行日志片段: logs/cron.log")
            for nl in test_res["new_logs"]:
                print(f"      {nl}")
        elif test_res["stderr"]:
            print(f"    错误输出:\n{test_res['stderr']}")

    # 体检总结与指导
    print("\n" + "=" * 68)
    if diag["overall_healthy"] and test_res["success"]:
        print("[体检结果] 系统定时器运行环境与配置完全健康！后台将按时精准静默打卡。")
    else:
        print("[体检结果] 定时器检测到以下需要注意或修复的事项:")
        for iss in diag["issues"]:
            print(f"  * [需修复] {iss}")
        for warn in diag["warnings"]:
            print(f"  * [需注意] {warn}")
    print("=" * 68)

if __name__ == "__main__":
    main()
