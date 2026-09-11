"""
水印照片生成模块 (watermark.py)
高保真还原网页前端 (xe / Me 函数) 的图片压缩与 Canvas 倾斜交错阵列水印算法。
支持在 PyCharm 中直接右键 Run / Debug，也支持通过命令行调用。
"""

import sys
import os

# 确保在 PyCharm 中无论从哪个层级运行，都能正确解析路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

import math
import io
import argparse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps

# 预设水印默认参数（完全对齐前端 $e / Me 参数）
DEFAULT_OPTIONS = {
    "angle_deg": -45,          # 水印倾斜角 -45°
    "spacing_x": 80,           # 水平间距 80px
    "spacing_y": 60,           # 垂直间距 60px
    "font_ratio": 0.032,       # 字体比例：图像短边的 3.2%
    "opacity": 0.35,           # 文字透明度 35%
    "shadow_opacity": 0.55,    # 阴影透明度 55%
    "quality": 85,             # 最终 JPEG 质量
    "max_dim": 1280,           # 长边最大分辨率 1280px (完全对齐前端 Me() 函数)
    "max_file_size_kb": int(os.getenv("MAX_PHOTO_SIZE_KB", "1024")) # 最大上传体积限制 (KB，默认 1MB)，超限自动压缩
}

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc"
]

def get_cjk_font(font_size: int) -> ImageFont.FreeTypeFont:
    """自动探测并加载中文字体"""
    for fp in FONT_CANDIDATES:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, font_size)
            except Exception:
                continue
    return ImageFont.load_default()

def format_watermark_text(user_name: str = "", slot_name: str = "", dt: datetime = None) -> str:
    """
    生成对齐前端 O() 函数的水印文本 (强制锁定东八区北京时间)
    格式：YYYY-MM-DD HH:mm · 姓名 · 时段名称
    """
    if dt is None:
        from config import get_beijing_now
        dt = get_beijing_now()
    time_str = dt.strftime("%Y-%m-%d %H:%M")
    parts = [time_str]
    if user_name:
        parts.append(user_name)
    if slot_name:
        parts.append(slot_name)
    return " · ".join(parts)

def resize_photo(img: Image.Image, max_dim: int = 1280) -> Image.Image:
    """
    对齐前端 Me() 函数：将图片长边缩放至不超过 max_dim (默认 1280px)
    """
    w, h = img.size
    scale = min(1.0, float(max_dim) / float(max(w, h)))
    if scale < 1.0:
        new_w = round(w * scale)
        new_h = round(h * scale)
        return img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return img

def apply_watermark(
    image_input,
    watermark_text: str,
    output_path: str = None,
    options: dict = None
) -> bytes:
    """
    为图片添加倾斜交错阵列水印 (完全还原前端 xe 函数)
    
    :param image_input: 图片文件路径、字节流 (bytes) 或 PIL.Image 对象
    :param watermark_text: 水印文字
    :param output_path: 保存路径（可选）
    :param options: 覆盖默认配置的字典
    :return: 最终合成后的 JPEG 字节流
    """
    opts = {**DEFAULT_OPTIONS, **(options or {})}
    
    # 1. 载入原始图片并按 EXIF Orientation 纠正旋转角度 (防止手机竖屏拍摄被误转为横屏)
    if isinstance(image_input, (str, bytes, io.BytesIO)):
        if isinstance(image_input, bytes):
            image_input = io.BytesIO(image_input)
        img = Image.open(image_input)
    elif isinstance(image_input, Image.Image):
        img = image_input
    else:
        raise ValueError("不支持的图片输入类型")

    # 核心修复：自动检测并应用手机照片中的 EXIF 旋转信息 (如 orientation=6 表示手机纵向竖拍)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    img = img.convert("RGB")
        
    # 2. 尺寸调整 (长边最大 1280px，完全对齐前端 Me() 函数)
    max_dim = opts.get("max_dim", 1280)
    img = resize_photo(img, max_dim=max_dim)
    w, h = img.size
    
    # 如果没有水印文字直接输出
    watermark_text = watermark_text.strip()
    if not watermark_text:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=opts["quality"])
        data = buf.getvalue()
        if output_path:
            with open(output_path, "wb") as f:
                f.write(data)
        return data

    # 3. 计算字号与字体
    min_dim = min(w, h)
    font_size = max(14, round(min_dim * opts["font_ratio"]))
    font = get_cjk_font(font_size)
    
    # 4. 计算文字物理尺寸与网格步长
    bbox = font.getbbox(watermark_text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    step_x = text_w + max(0, opts["spacing_x"])
    step_y = font_size + max(0, opts["spacing_y"])
    
    # 对角线计算与防留白外扩
    diagonal = math.ceil(math.hypot(w, h)) + font_size * 4
    diag = int(diagonal)
    if diag % 2 != 0:
        diag += 1
        
    # 行列数与起始坐标
    rows = math.ceil(diag / step_y) + 1
    cols = math.ceil(diag / step_x) + 1
    start_y = -rows * step_y / 2
    start_x = -cols * step_x / 2
    
    # 5. 创建透明离屏图层并绘制阴影与文字
    watermark_layer = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark_layer)
    cx, cy = diag / 2, diag / 2
    
    shadow_color = (0, 0, 0, int(255 * opts["shadow_opacity"]))
    text_color = (255, 255, 255, int(255 * opts["opacity"]))
    
    for r in range(rows + 1):
        offset_x = (r % 2) * (step_x / 2) # 奇偶行交错偏移
        y = start_y + r * step_y + cy
        for c in range(cols + 1):
            x = start_x + c * step_x + offset_x + cx
            # 绘制黑底文字阴影 (偏移 1px, 1px)
            draw.text((x + 1, y + 1), watermark_text, font=font, fill=shadow_color, anchor="mm")
            # 绘制白色半透明文字
            draw.text((x, y), watermark_text, font=font, fill=text_color, anchor="mm")
            
    # 6. 旋转与居中裁切 (-45° 旋转)
    rotated = watermark_layer.rotate(45, resample=Image.Resampling.BICUBIC)
    crop_x1 = (diag - w) // 2
    crop_y1 = (diag - h) // 2
    cropped = rotated.crop((crop_x1, crop_y1, crop_x1 + w, crop_y1 + h))
    
    # 7. 合成图层并导出为 JPEG，具备智能文件大小自适应压缩控制 (防止触碰服务端上传文件体积上限)
    base_rgba = img.convert("RGBA")
    combined = Image.alpha_composite(base_rgba, cropped).convert("RGB")
    
    max_kb = opts.get("max_file_size_kb", 1024)
    curr_quality = opts.get("quality", 85)
    curr_img = combined
    
    buf = io.BytesIO()
    curr_img.save(buf, format="JPEG", quality=curr_quality)
    result_bytes = buf.getvalue()
    
    # 若文件体积超出限制 (默认 1024KB)，动态递进降低 JPEG 质量或微调尺寸直至合格
    attempts = 0
    while len(result_bytes) > max_kb * 1024 and (curr_quality > 35 or curr_img.width > 480) and attempts < 8:
        attempts += 1
        if curr_quality > 45:
            curr_quality -= 10
        else:
            new_w = max(480, round(curr_img.width * 0.85))
            new_h = max(480, round(curr_img.height * 0.85))
            curr_img = curr_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        curr_img.save(buf, format="JPEG", quality=curr_quality)
        result_bytes = buf.getvalue()
        
    final_w, final_h = curr_img.size
    
    if output_path:
        # 确保输出目录存在
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(result_bytes)
        print(f"[+] 水印照片已成功生成并保存至: {output_path} (尺寸: {final_w}x{final_h}, 大小: {len(result_bytes)/1024:.1f} KB)")
        
    return result_bytes

# ==================== PyCharm 直接运行 / 调试入口 ====================
if __name__ == "__main__":
    # 如果在 PyCharm 中直接点击 Run / Debug 且未提供命令行参数：
    if len(sys.argv) == 1:
        print("[*] PyCharm 调试模式启动 (未输入命令行参数，使用默认测试图)...")
        # 探测测试图片
        test_inputs = [
            os.path.join(PARENT_DIR, "test_base.jpg"),
            os.path.join(CURRENT_DIR, "test_base.jpg"),
            os.path.join(CURRENT_DIR, "sample_watermark.jpg")
        ]
        sample_in = None
        for p in test_inputs:
            if os.path.exists(p):
                sample_in = p
                break
                
        if not sample_in:
            # 自动生成一张简单的测试图片
            sample_in = os.path.join(CURRENT_DIR, "test_base.jpg")
            img = Image.new("RGB", (1280, 720), color=(100, 140, 190))
            img.save(sample_in)
            print(f"[+] 自动生成测试图片: {sample_in}")

        sample_out = os.path.join(CURRENT_DIR, "pycharm_debug_watermark.jpg")
        test_text = format_watermark_text(user_name="", slot_name="打卡测试")
        print(f"[*] 输入文件: {sample_in}")
        print(f"[*] 输出文件: {sample_out}")
        print(f"[*] 水印内容: {test_text}")
        apply_watermark(sample_in, test_text, output_path=sample_out)
        print(f"[🎉] 调试生成完成！您可以在 PyCharm 左侧双击打开查看: pycharm_debug_watermark.jpg")
    else:
        parser = argparse.ArgumentParser(description="学搭子 (kassing.cn) 水印照片独立生成工具")
        parser.add_argument("input", help="输入原始照片路径")
        parser.add_argument("-o", "--output", default="watermarked.jpg", help="输出图片路径 (默认: watermarked.jpg)")
        parser.add_argument("--name", default="", help="打卡人姓名")
        parser.add_argument("--slot", default="日常打卡", help="打卡时段名称 (如: 晚自习 / 早读)")
        parser.add_argument("--text", default="", help="直接指定完整水印文字 (覆盖 --name 与 --slot)")
        parser.add_argument("--time", default="", help="自定义时间 (格式: YYYY-MM-DD HH:mm，默认当前时间)")
        
        args = parser.parse_args()
        
        if args.text:
            wm_text = args.text
        else:
            dt = datetime.strptime(args.time, "%Y-%m-%d %H:%M") if args.time else None
            wm_text = format_watermark_text(user_name=args.name, slot_name=args.slot, dt=dt)
            
        print(f"[*] 正在为图片 [{args.input}] 生成水印...")
        print(f"[*] 水印内容: {wm_text}")
        apply_watermark(args.input, wm_text, output_path=args.output)
