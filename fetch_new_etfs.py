# -*- coding: utf-8 -*-
"""
拉取新增ETF的历史数据
执行：python fetch_new_etfs.py
"""
import sys
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.data_fetcher import fetch_etf_data, save_to_db

# 新增的7只ETF
NEW_ETFS = {
    '512290': '生物医药ETF',
    '513520': '恒生科技ETF',
    '510580': '500ETF',
    '512680': '化工ETF',
    '515030': '新能源车ETF',
    '512170': '医疗ETF',
    '159605': '人工智能ETF',
}

print("=== 拉取新增ETF历史数据 ===\n")
print(f"共 {len(NEW_ETFS)} 只ETF需要更新\n")

success = []
failed = []

for code, name in NEW_ETFS.items():
    print(f"正在拉取 {code} ({name})...", end=' ')
    try:
        df = fetch_etf_data(code, days=800)
        if df is not None and not df.empty:
            save_to_db(df, code)
            print(f"✓ 成功 ({len(df)} 条记录)")
            success.append(code)
        else:
            print(f"✗ 失败：无数据")
            failed.append(code)
    except Exception as e:
        print(f"✗ 失败：{e}")
        failed.append(code)

print(f"\n=== 拉取完成 ===")
print(f"成功：{len(success)} 只")
print(f"失败：{len(failed)} 只")

if failed:
    print(f"\n失败列表：{', '.join(failed)}")
    print("建议：稍后重试或检查代码有效性")

