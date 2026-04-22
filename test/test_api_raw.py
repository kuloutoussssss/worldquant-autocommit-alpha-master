# -*- coding: utf-8 -*-
"""测试 API 原始响应"""
import sys
sys.path.insert(0, '.')

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from requests.auth import HTTPBasicAuth
import os
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = 'https://api.worldquantbrain.com'
username = os.getenv("WQ_USERNAME")
password = os.getenv("WQ_PASSWORD")

print(f"[*] Username: {username}")
print(f"[*] Password set: {bool(password)}")

session = requests.Session()
session.auth = HTTPBasicAuth(username, password)
session.trust_env = False

# 认证
print("\n[*] Authenticating...")
resp = session.post(f"{API_BASE_URL}/authentication")
print(f"[*] Auth status: {resp.status_code}")
print(f"[*] Auth response: {resp.text[:200]}")

# 获取用户信息
print("\n[*] Getting user info...")
resp = session.get(f"{API_BASE_URL}/users/self")
print(f"[*] User status: {resp.status_code}")
if resp.status_code == 200:
    user_data = resp.json()
    print(f"[*] User: {user_data.get('email')}, ID: {user_data.get('id')}")

# 获取用户 Alpha 列表
print("\n[*] Getting /users/self/alphas...")
params = {"limit": 10, "offset": 0, "hidden": False, "order": "-dateCreated"}
resp = session.get(f"{API_BASE_URL}/users/self/alphas", params=params)
print(f"[*] Status: {resp.status_code}")
print(f"[*] Headers: {dict(resp.headers)}")
print(f"[*] Response: {resp.text[:1000]}")

# 尝试其他端点
print("\n[*] Trying /alphas...")
resp = session.get(f"{API_BASE_URL}/alphas", params={"limit": 5})
print(f"[*] Status: {resp.status_code}")
print(f"[*] Response: {resp.text[:500]}")
