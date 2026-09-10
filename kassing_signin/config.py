"""
配置与工具模块 (config.py)
自动解析 .env / .config 配置文件，支持动态读取用户名密码、在指定范围内随机生成经纬度、
基于【动态冷却期算法】与【最低照片池联动约束】在 PhotoStorage/ 目录中随机选取底图。
"""

import os
import json
import glob
import math
import random
from datetime import datetime, timezone, timedelta

# 锁定北京时间 (东八区 UTC+8)，彻底防止系统时区异常、0时区或防追踪机制导致的时间偏差
BEIJING_TZ = timezone(timedelta(hours=8))

def get_beijing_now() -> datetime:
    """获取标准的东八区北京时间 (无论宿主机是什么时区)"""
    return datetime.now(BEIJING_TZ)

def format_iso_to_cst(iso_str: str) -> str:
    """将官方服务端返回的 ISO 8601 UTC 时间字符串 (例如 2026-09-09T00:16:42.936Z) 转换为东八区北京时间 (YYYY-MM-DD HH:MM:SS)"""
    if not iso_str:
        return "--"
    try:
        clean_str = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        dt_cst = dt.astimezone(BEIJING_TZ)
        return dt_cst.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_str

def format_record_status(status_raw: str) -> str:
    """将官方接口返回的英文打卡状态转为中文"""
    if not status_raw:
        return "正常"
    status_map = {
        "normal": "正常",
        "late": "迟到",
        "leave": "请假",
        "absent": "缺勤",
        "appeal": "申诉中",
    }
    return status_map.get(str(status_raw).lower(), str(status_raw))

# 定位当前工程根目录
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PACKAGE_DIR)
PHOTOSTORAGE_DIR = os.path.join(PROJECT_ROOT, "PhotoStorage")
ARCHIVES_DIR = os.path.join(PROJECT_ROOT, "Archives")

# 保持向后兼容别名
PHOTOSTORE_DIR = PHOTOSTORAGE_DIR
INPUTS_DIR = PHOTOSTORAGE_DIR
OUTPUTS_DIR = ARCHIVES_DIR

PHOTO_HISTORY_FILE = os.path.join(PHOTOSTORAGE_DIR, ".photo_history.json")

os.makedirs(PHOTOSTORAGE_DIR, exist_ok=True)
os.makedirs(ARCHIVES_DIR, exist_ok=True)

def load_env_file(env_path: str = None) -> dict:
    """轻量级直接解析 .env 或 .config 文件，无需引入额外三方依赖"""
    if env_path is None:
        for candidate in [os.path.join(PROJECT_ROOT, ".env"), os.path.join(PROJECT_ROOT, ".config")]:
            if os.path.exists(candidate):
                env_path = candidate
                break
                
    config_dict = {}
    if env_path and os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    config_dict[k] = v
    return config_dict

_ENV_DATA = load_env_file()

def get_config_val(key: str, default: str = "") -> str:
    """优先从系统环境变量读取，其次从配置文件读取，最后返回默认值"""
    return os.getenv(key, _ENV_DATA.get(key, default))

def _safe_float(val: str, default: float) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def _safe_int(val: str, default: int) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

# a. 登录账号
DEFAULT_ACCOUNT = get_config_val("ACCOUNT", "")

# b. 登录密码
DEFAULT_PASSWORD = get_config_val("PASSWORD", "")

# c. 距离总部的距离范围 (单位: 米)
DISTANCE_RANGE_METERS = _safe_float(get_config_val("DISTANCE_RANGE_METERS", "50"), 50.0)

# d. 照片冷却期次数 (系统规定最低为 9 次，对应覆盖连续 3 天早中晚 9 次打卡)
PHOTO_COOLDOWN_COUNT = max(9, _safe_int(get_config_val("PHOTO_COOLDOWN_COUNT", "9"), 9))

# e. 上传图片最大文件体积限制 (单位: KB，默认 1024 即 1MB)
MAX_PHOTO_SIZE_KB = _safe_int(get_config_val("MAX_PHOTO_SIZE_KB", "1024"), 1024)

# 总部基准经纬度 (高德 GCJ-02)
HQ_LATITUDE = _safe_float(get_config_val("HQ_LATITUDE", "34.802958"), 34.802958)
HQ_LONGITUDE = _safe_float(get_config_val("HQ_LONGITUDE", "113.544171"), 113.544171)

# 精度随机区间
ACCURACY_MIN = _safe_int(get_config_val("ACCURACY_MIN", "35"), 35)
ACCURACY_MAX = _safe_int(get_config_val("ACCURACY_MAX", "65"), 65)

# API 地址
BASE_URL = get_config_val("BASE_URL", "https://www.kassing.cn")

# 字体候选
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

def validate_env_config() -> tuple:
    """
    检查 .env 配置文件是否存在以及内部关键参数的合法性。
    返回: (is_valid: bool, errors: list[str])
    """
    env_file_exists = False
    for candidate in [os.path.join(PROJECT_ROOT, ".env"), os.path.join(PROJECT_ROOT, ".config")]:
        if os.path.exists(candidate):
            env_file_exists = True
            break

    if not env_file_exists:
        return False, ["未检测到配置文件 .env"]

    errors = []
    
    # 1. 账号与密码校验
    account = get_config_val("ACCOUNT", "").strip()
    password = get_config_val("PASSWORD", "").strip()
    if not account:
        errors.append("登录账号 (ACCOUNT) 为空或未配置")
    if not password:
        errors.append("登录密码 (PASSWORD) 为空或未配置")

    # 2. 定位半径校验 (0 < 半径 <= 150)
    raw_dist = get_config_val("DISTANCE_RANGE_METERS", "").strip()
    if not raw_dist:
        errors.append("定位半径 (DISTANCE_RANGE_METERS) 未配置")
    else:
        try:
            dist = float(raw_dist)
            if dist <= 0 or dist > 150:
                errors.append(f"定位半径 (DISTANCE_RANGE_METERS={dist}) 异常: 数值必须在 0 到 150 米之间 (0 < 半径 <= 150)")
        except ValueError:
            errors.append(f"定位半径 (DISTANCE_RANGE_METERS='{raw_dist}') 格式无效，必须为数字")

    # 3. 冷却池数量校验 (整数且 >= 9)
    raw_cooldown = get_config_val("PHOTO_COOLDOWN_COUNT", "").strip()
    if not raw_cooldown:
        errors.append("照片冷却池数量 (PHOTO_COOLDOWN_COUNT) 未配置")
    else:
        try:
            cd = int(raw_cooldown)
            if cd < 9:
                errors.append(f"照片冷却池数量 (PHOTO_COOLDOWN_COUNT={cd}) 异常: 系统规定不能低于 9 次")
        except ValueError:
            errors.append(f"照片冷却池数量 (PHOTO_COOLDOWN_COUNT='{raw_cooldown}') 格式无效，必须为整数且 >= 9")

    # 4. 图片体积限制校验
    raw_size = get_config_val("MAX_PHOTO_SIZE_KB", "").strip()
    if raw_size:
        try:
            sz = int(raw_size)
            if sz <= 0:
                errors.append(f"最大图片体积 (MAX_PHOTO_SIZE_KB={sz}) 异常: 必须大于 0")
        except ValueError:
            errors.append(f"最大图片体积 (MAX_PHOTO_SIZE_KB='{raw_size}') 格式无效，必须为整数")

    return (len(errors) == 0, errors)

def reload_config():
    """重新加载 .env 配置文件"""
    global _ENV_DATA, DEFAULT_ACCOUNT, DEFAULT_PASSWORD, DISTANCE_RANGE_METERS
    global PHOTO_COOLDOWN_COUNT, MAX_PHOTO_SIZE_KB, HQ_LATITUDE, HQ_LONGITUDE
    _ENV_DATA = load_env_file()
    DEFAULT_ACCOUNT = get_config_val("ACCOUNT", "")
    DEFAULT_PASSWORD = get_config_val("PASSWORD", "")
    DISTANCE_RANGE_METERS = _safe_float(get_config_val("DISTANCE_RANGE_METERS", "50"), 50.0)
    PHOTO_COOLDOWN_COUNT = max(9, _safe_int(get_config_val("PHOTO_COOLDOWN_COUNT", "9"), 9))
    MAX_PHOTO_SIZE_KB = _safe_int(get_config_val("MAX_PHOTO_SIZE_KB", "1024"), 1024)
    HQ_LATITUDE = _safe_float(get_config_val("HQ_LATITUDE", "34.802958"), 34.802958)
    HQ_LONGITUDE = _safe_float(get_config_val("HQ_LONGITUDE", "113.544171"), 113.544171)

def count_input_photos() -> int:
    """统计 PhotoStorage/ 目录下的有效打卡底图总数"""
    valid_exts = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp")
    all_photos = []
    for ext in valid_exts:
        all_photos.extend(glob.glob(os.path.join(PHOTOSTORAGE_DIR, ext)))
        all_photos.extend(glob.glob(os.path.join(PHOTOSTORAGE_DIR, ext.upper())))
    all_photos = [p for p in all_photos if not os.path.basename(p).startswith(".")]
    return len(all_photos)

# 别名兼容
count_photostorage_photos = count_input_photos
count_photostore_photos = count_input_photos

def get_min_photo_pool_size(cooldown: int = None) -> int:
    """
    计算照片池最低容量限制:
    冷却池 + 8 张 (冷却池系统规定最低为 9，对应总底图数最低为 9 + 8 = 17 张)
    """
    if cooldown is None:
        cooldown = PHOTO_COOLDOWN_COUNT
    cooldown = max(9, cooldown)
    return cooldown + 8

def get_random_location(
    hq_lat: float = None,
    hq_lng: float = None,
    max_distance_meters: float = None
) -> tuple:
    """
    在距离总部指定米数的圆形范围内，【均匀随机】生成一个经纬度坐标
    :return: (rand_lat, rand_lng, rand_accuracy, actual_distance_meters)
    """
    if hq_lat is None:
        hq_lat = HQ_LATITUDE
    if hq_lng is None:
        hq_lng = HQ_LONGITUDE
    if max_distance_meters is None:
        max_distance_meters = DISTANCE_RANGE_METERS
        
    r = max_distance_meters * math.sqrt(random.uniform(0.04, 1.0))
    theta = random.uniform(0, 2 * math.pi)
    
    dy = r * math.sin(theta)
    delta_lat = dy / 111320.0
    
    dx = r * math.cos(theta)
    delta_lng = dx / (111320.0 * math.cos(math.radians(hq_lat)))
    
    rand_lat = round(hq_lat + delta_lat, 6)
    rand_lng = round(hq_lng + delta_lng, 6)
    rand_acc = random.randint(ACCURACY_MIN, ACCURACY_MAX)
    
    actual_distance = round(r, 1)
    return rand_lat, rand_lng, rand_acc, actual_distance

# ==================== 智能照片冷却池算法 ====================

def _load_photo_history() -> list:
    """读取照片使用历史记录列表（越靠后越近期）"""
    if os.path.exists(PHOTO_HISTORY_FILE):
        try:
            with open(PHOTO_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []

def _save_photo_history(history: list):
    """持久化保存照片使用历史"""
    try:
        with open(PHOTO_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] 警告: 保存照片历史记录失败: {e}")

def get_random_input_image(record_history: bool = True) -> str:
    """
    基于【动态冷却期】与【最低照片池容量门槛】从 PhotoStorage/ 中抽取底图：
    - 校验照片池总数是否达到最低下限 N_min = 冷却池大小 + 缓冲量 Buffer；
    - 最近选中的 X 张照片进入冷却期，暂时移出候选池；
    - 超过 X 次后自动解除冷却，重返候选池。
    
    :param record_history: 是否将本次选中记录计入历史冷却期
    :return: 选中图片的绝对路径
    """
    valid_exts = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp")
    all_photos = []
    for ext in valid_exts:
        all_photos.extend(glob.glob(os.path.join(PHOTOSTORAGE_DIR, ext)))
        all_photos.extend(glob.glob(os.path.join(PHOTOSTORAGE_DIR, ext.upper())))
        
    all_photos = [p for p in all_photos if not os.path.basename(p).startswith(".")]
    total_count = len(all_photos)
    
    if total_count == 0:
        raise FileNotFoundError(f"PhotoStorage 文件夹 ({PHOTOSTORAGE_DIR}) 中未找到任何可用图片！请放入待打卡底图。")
        
    # 核心约束：校验总照片池是否满足最低限度要求 (冷却池 + 8 张)
    min_required = get_min_photo_pool_size()
    if total_count < min_required:
        raise ValueError(
            f"[错误] 照片池底图数量不足，程序拒绝运行。\n"
            f"当前设定照片冷却池为 {PHOTO_COOLDOWN_COUNT} 张（系统最低要求 9 张），总照片数量必须达到 冷却池 + 8 = {min_required} 张。\n"
            f"当前 PhotoStorage/ 目录下仅检测到 {total_count} 张有效照片。\n"
            f"为了防范平台机械重复审查风险，请往 PhotoStorage/ 目录上传更多不同场景下的打卡照片（至少还需补充 {min_required - total_count} 张）后再运行。"
        )
        
    photo_map = {os.path.basename(p): p for p in all_photos}
    all_filenames = set(photo_map.keys())
    
    # 1. 读取历史记录并剔除已从磁盘删除的照片
    history = [fn for fn in _load_photo_history() if fn in all_filenames]
    
    # 2. 计算当前冷却池
    cooldown_photos = set(history[-PHOTO_COOLDOWN_COUNT:]) if PHOTO_COOLDOWN_COUNT > 0 else set()
    
    # 3. 候选池 = 所有照片 - 冷却中的照片
    available_filenames = list(all_filenames - cooldown_photos)
    if not available_filenames:
        available_filenames = [history[0]] if history else list(all_filenames)
        
    # 4. 从可用候选池中随机抽取
    selected_filename = random.choice(available_filenames)
    selected_path = photo_map[selected_filename]
    
    # 5. 更新历史队列
    if record_history:
        if selected_filename in history:
            history.remove(selected_filename)
        history.append(selected_filename)
        max_keep = max(20, PHOTO_COOLDOWN_COUNT * 4)
        history = history[-max_keep:]
        _save_photo_history(history)
        
    # 打印详细冷却状态日志
    print(f"      [照片选择机制] 照片池共 {total_count} 张 (门槛: 冷却池 {PHOTO_COOLDOWN_COUNT} + 8 = {min_required} 张) | 冷却期: {PHOTO_COOLDOWN_COUNT} 次 | 可用候选: {len(available_filenames)} 张")
    if cooldown_photos:
        print(f"      [当前冷却中] ({len(cooldown_photos)} 张): {', '.join(cooldown_photos)}")
    print(f"      [本次中选] {selected_filename} (剩余可用候选: {len(available_filenames)} 张)")
    
    return selected_path

def get_output_image_path(slot_name: str = "signin") -> str:
    """在 Archives 文件夹中按北京时间戳与时段名生成归档路径"""
    timestamp = get_beijing_now().strftime("%Y%m%d_%H%M%S")
    clean_slot = "".join([c for c in slot_name if c.isalnum() or c in ("_", "-")]) or "signin"
    filename = f"watermarked_{timestamp}_{clean_slot}.jpg"
    return os.path.join(ARCHIVES_DIR, filename)

# 兼容别名
DEFAULT_LATITUDE = HQ_LATITUDE
DEFAULT_LONGITUDE = HQ_LONGITUDE
DEFAULT_ACCURACY = 58
