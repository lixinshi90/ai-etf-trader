# -*- coding: utf-8 -*-
import requests
import json
import time
import sys

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("Waiting for server restart...")
time.sleep(2)

print("\n=== 最终修复验证 ===\n")

# Test portfolio API
print("1. 测试 /api/portfolio:")
try:
    resp = requests.get('http://127.0.0.1:5001/api/portfolio', timeout=5)
    data = resp.json()
    
    print(f"   状态: {resp.status_code}")
    print(f"   总资产: {data.get('total_value'):.2f}")
    print(f"   现金: {data.get('cash'):.2f}")
    print(f"   持仓市值: {data.get('holdings_value'):.2f}")
    print(f"   持仓数量: {len(data.get('positions', []))}")
    
    # Verify
    total = data.get('total_value', 0)
    if 99000 < total < 100000:
        print(f"   ✓ 总资产在合理范围内 (99000-100000)")
    else:
        print(f"   ✗ 总资产异常: {total:.2f}")
        
except Exception as e:
    print(f"   错误: {e}")

# Test trades count
print("\n2. 测试交易次数:")
try:
    resp = requests.get('http://127.0.0.1:5001/api/trades', timeout=5)
    trades = resp.json()
    print(f"   交易记录数: {len(trades)}")
    
    if len(trades) == 43:
        print(f"   ✓ 交易次数正确 (43)")
    else:
        print(f"   ✗ 交易次数异常: {len(trades)}")
        
except Exception as e:
    print(f"   错误: {e}")

print("\n=== 验证完成 ===")

