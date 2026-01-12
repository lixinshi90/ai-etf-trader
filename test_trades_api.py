# -*- coding: utf-8 -*-
import requests
import sys

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 测试 /api/trades 接口 ===\n")

try:
    response = requests.get('http://127.0.0.1:5001/api/trades', timeout=5)
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ 成功，返回 {len(data)} 条记录")
    else:
        print(f"✗ 错误: {response.status_code}")
        print(f"响应内容: {response.text[:500]}")
        
except Exception as e:
    print(f"✗ 请求失败: {e}")
    import traceback
    traceback.print_exc()

