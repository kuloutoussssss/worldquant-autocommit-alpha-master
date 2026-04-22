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

session = requests.Session()
session.auth = HTTPBasicAuth(username, password)
session.trust_env = False

# 认证
session.post(f"{API_BASE_URL}/authentication")

# 获取用户 Alpha 列表 - 测试不同参数组合
print("[*] Testing /users/self/alphas with different params...")

# 测试1: 不带 hidden 参数
print("\n[1] Without hidden param:")
resp = session.get(f"{API_BASE_URL}/users/self/alphas", params={"limit": 5, "offset": 0})
print(f"    Status: {resp.status_code}")
print(f"    Response: {resp.text[:500]}")

# 测试2: 只带 limit 和 offset
print("\n[2] Only limit + offset:")
resp = session.get(f"{API_BASE_URL}/users/self/alphas", params={"limit": 5, "offset": 0, "order": "-dateCreated"})
print(f"    Status: {resp.status_code}")
print(f"    Response: {resp.text[:500]}")

# 测试3: 带 stage
print("\n[3] With stage='SIM':")
resp = session.get(f"{API_BASE_URL}/users/self/alphas", params={"limit": 5, "offset": 0, "stage": "SIM"})
print(f"    Status: {resp.status_code}")
print(f"    Response: {resp.text[:500]}")
