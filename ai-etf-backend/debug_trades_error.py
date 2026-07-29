# -*- coding: utf-8 -*-
"""
调试 /api/trades 接口的 500 错误
"""
import sys
import sqlite3
import pandas as pd
import json

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 调试 /api/trades 错误 ===\n")

# 1. 直接从数据库读取
print("1. 从数据库读取交易记录:")
try:
    conn = sqlite3.connect('data/trade_history.db')
    df = pd.read_sql_query("SELECT * FROM trades ORDER BY datetime(date) DESC LIMIT 5", conn)
    conn.close()
    
    print(f"记录数: {len(df)}")
    print(f"列名: {list(df.columns)}")
    print("\n前5条记录:")
    print(df.to_string(index=False))
    
    # 检查是否有 NaN 值
    print("\n检查 NaN 值:")
    for col in df.columns:
        nan_count = df[col].isna().sum()
        if nan_count > 0:
            print(f"  {col}: {nan_count} 个 NaN")
    
    # 尝试转换为 JSON
    print("\n2. 尝试转换为 JSON:")
    try:
        # 模拟 web_app.py 的处理流程
        df_clean = df.replace(to_replace=["NaN", "nan", "None", "null", "NaT", ""], value=pd.NA)
        df_clean = df_clean.where(pd.notna(df_clean), None)
        if 'id' in df_clean.columns:
            df_clean = df_clean.drop(columns=['id'])
        
        recs = df_clean.to_dict("records")
        
        # 检查每条记录
        for i, rec in enumerate(recs[:3]):
            print(f"\n记录 {i+1}:")
            for key, value in rec.items():
                value_type = type(value).__name__
                is_nan = pd.isna(value) if value is not None else False
                print(f"  {key}: {value} (type: {value_type}, isNaN: {is_nan})")
        
        # 尝试 JSON 序列化
        json_str = json.dumps(recs, allow_nan=False, default=str)
        print(f"\n✓ JSON 序列化成功，长度: {len(json_str)}")
        
    except Exception as e:
        print(f"\n✗ JSON 序列化失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 找出问题字段
        print("\n查找问题字段:")
        for i, rec in enumerate(recs):
            for key, value in rec.items():
                try:
                    json.dumps({key: value}, allow_nan=False)
                except Exception:
                    print(f"  记录 {i}, 字段 {key}: {value} (type: {type(value)})")
        
except Exception as e:
    print(f"✗ 数据库读取失败: {e}")
    import traceback
    traceback.print_exc()

print("\n=== 调试完成 ===")

