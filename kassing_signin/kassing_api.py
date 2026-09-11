"""
网络请求与网站 API 交互模块 (kassing_api.py)
对齐 kassing.cn 前端接口规范，包含登录、时段查询、照片上传与签到记录提交。
支持在 PyCharm 中直接右键 Run / Debug。
"""

import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

import requests
from typing import Dict, Any, List, Optional
from config import BASE_URL, DEFAULT_ACCOUNT, DEFAULT_PASSWORD, DEFAULT_LATITUDE, DEFAULT_LONGITUDE, DEFAULT_ACCURACY

class KassingAPI:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
        })
        self.token: Optional[str] = None
        self.user_profile: Dict[str, Any] = {}

    def login(self, account: str = DEFAULT_ACCOUNT, password: str = DEFAULT_PASSWORD) -> Dict[str, Any]:
        """
        账号密码登录接口 (POST /api/auth/login-account)
        """
        url = f"{self.base_url}/api/auth/login-account"
        payload = {
            "account": account.strip(),
            "password": password.strip()
        }
        resp = self.session.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        body = data.get("data", data) if isinstance(data, dict) and "data" in data else data
        self.token = body.get("token")
        if not self.token:
            raise ValueError(f"登录失败，未收到有效 Token: {data}")
            
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        self.user_profile = body.get("profile", {})
        
        user_name = self.user_profile.get("name", account)
        print(f"[+] 登录成功！欢迎，{user_name} | 用户名: {self.user_profile.get('no', account)}")
        return body

    def get_today_slots(self) -> List[Dict[str, Any]]:
        """
        查询今日签到时段与打卡状态 (GET /api/signin/today)
        """
        url = f"{self.base_url}/api/signin/today"
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        slots = data.get("data", data) if isinstance(data, dict) and "data" in data else data
        return slots if isinstance(slots, list) else []

    def upload_photo(self, photo_bytes: bytes, filename: str = "signin.jpg", biz: str = "signin") -> str:
        """
        上传水印打卡图片 (POST /api/upload/file)
        :return: 上传后的图片 key / url
        """
        url = f"{self.base_url}/api/upload/file"
        files = {
            "file": (filename, photo_bytes, "image/jpeg")
        }
        data = {
            "biz": biz
        }
        resp = self.session.post(url, files=files, data=data, timeout=30)
        resp.raise_for_status()
        res_json = resp.json()
        res_data = res_json.get("data", res_json) if isinstance(res_json, dict) and "data" in res_json else res_json
        
        photo_key = res_data.get("key") or res_data.get("url") or res_data.get("path")
        if not photo_key:
            raise ValueError(f"文件上传失败，未能提取到图片 key: {res_json}")
            
        print(f"[+] 照片上传成功，云端存储 Key: {photo_key}")
        return photo_key

    def submit_record(
        self,
        slot_id: str,
        location_id: str,
        photo_url: str,
        latitude: float = DEFAULT_LATITUDE,
        longitude: float = DEFAULT_LONGITUDE,
        accuracy: float = DEFAULT_ACCURACY
    ) -> Dict[str, Any]:
        """
        提交最终签到打卡记录 (POST /api/signin/regular/record)
        """
        url = f"{self.base_url}/api/signin/regular/record"
        payload = {
            "slotId": slot_id,
            "locationId": location_id,
            "photoUrl": photo_url,
            "latitude": round(float(latitude), 6),
            "longitude": round(float(longitude), 6),
            "accuracy": round(float(accuracy))
        }
        resp = self.session.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        res_json = resp.json()
        print(f"[+] 签到打卡提交成功！响应: {res_json}")
        return res_json

# ==================== PyCharm 直接运行 / 调试入口 ====================
if __name__ == "__main__":
    print("[*] PyCharm 调试模式启动: 正在测试 kassing_api.py 登录与时段拉取...")
    api = KassingAPI()
    api.login()
    slots = api.get_today_slots()
    print(f"\n[+] 成功拉取到今日时段配置，共有 {len(slots)} 个时段:")
    for s in slots:
        print(f"    - {s.get('name')} ({s.get('startTime')} ~ {s.get('endTime')}): signed={s.get('signed')}")
    print("\n[🎉] kassing_api.py API 接口联调正常！")
