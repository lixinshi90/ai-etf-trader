# -*- coding: utf-8 -*-
import sys
import pandas as pd
import sqlite3
from datetime import datetime

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 今日状态检查 ===\n")

# 1. 检查今天是否为交易日
today = pd.Timestamp.today()
today_str = today.strftime('%Y-%m-%d')
print(f"今天日期: {today_str}")
print(f"星期: {['一', '二', '三', '四', '五', '六', '日'][today.weekday()]}")

# 使用akshare检查交易日
try:
    import akshare as ak
    trade_cal = ak.tool_trade_date_hist_sina()
    trading_days = set(pd.to_datetime(trade_cal['trade_date']).dt.strftime('%Y-%m-%d'))
    
    is_trading = today_str in trading_days
    print(f"是否为交易日: {'✓ 是' if is_trading else '✗ 否（周末或节假日）'}")
    
    if not is_trading:
        # 找最近的交易日
        recent_trading = sorted([d for d in trading_days if d < today_str], reverse=True)
        if recent_trading:
            print(f"最近交易日: {recent_trading[0]}")
except Exception as e:
    print(f"无法获取交易日历: {e}")
    print(f"简单判断: {'✓ 是（工作日）' if today.weekday() < 5 else '✗ 否（周末）'}")

# 2. 检查今日是否已有数据
print("\n=== 数据库检查 ===\n")

conn = sqlite3.connect('data/trade_history.db')

# 检查今日是否有交易记录
df_today_trades = pd.read_sql_query(
    f"SELECT * FROM trades WHERE date >= '{today_str}' ORDER BY date",
    conn
)
print(f"今日交易记录: {len(df_today_trades)} 笔")
if len(df_today_trades) > 0:
    print("详情:")
    for _, row in df_today_trades.iterrows():
        print(f"  {row['date']} {row['etf_code']} {row['action']} {row['quantity']:.2f}")

# 检查今日是否有净值记录
df_today_equity = pd.read_sql_query(
    f"SELECT * FROM daily_equity WHERE date = '{today_str}'",
    conn
)
print(f"\n今日净值记录: {'✓ 有' if len(df_today_equity) > 0 else '✗ 无'}")
if len(df_today_equity) > 0:
    print(f"  净值: {df_today_equity.iloc[0]['equity']:.2f}")

# 检查最新净值
df_latest = pd.read_sql_query(
    "SELECT date, equity FROM daily_equity ORDER BY date DESC LIMIT 1",
    conn
)
print(f"\n最新净值记录:")
print(f"  日期: {df_latest.iloc[0]['date']}")
print(f"  净值: {df_latest.iloc[0]['equity']:.2f}")

conn.close()

# 3. 检查AI决策文件
print("\n=== AI决策文件检查 ===\n")

import os
import glob

decisions_dir = 'decisions'
if os.path.exists(decisions_dir):
    today_decisions = glob.glob(f"{decisions_dir}/{today_str.replace('-', '')}*.json")
    print(f"今日决策文件: {len(today_decisions)} 个")
    if today_decisions:
        print("文件列表:")
        for f in today_decisions[:5]:
            print(f"  {os.path.basename(f)}")
else:
    print("decisions 目录不存在")

# 4. 重新执行的影响分析
print("\n=== 重新执行任务的影响分析 ===\n")

print("如果今天是交易日且已执行过任务：")
print("  ✓ 优点：")
print("    - 可以使用新的AI调用上限（8次）")
print("    - 可以应用新的风控参数")
print("    - 可以让新增的7只ETF参与决策")
print("\n  ⚠️ 风险：")
print("    - 会覆盖今日已有的交易记录")
print("    - 可能产生不同的交易决策")
print("    - 需要确保数据库已备份")

print("\n如果今天不是交易日：")
print("  ✗ 不建议执行：")
print("    - 无法获取实时行情")
print("    - 交易所不开市，无法交易")
print("    - 应等待下一个交易日")

print("\n=== 建议 ===\n")

if len(df_today_trades) > 0 or len(df_today_equity) > 0:
    print("⚠️ 今日已有数据，重新执行会覆盖！")
    print("\n建议操作：")
    print("1. 先备份数据库：")
    print("   copy data\\trade_history.db data\\trade_history.backup_before_rerun.db")
    print("\n2. 调整AI调用上限：")
    print("   在 .env 中修改 DAILY_AI_CALLS_LIMIT=12 （或其他值）")
    print("\n3. 重新执行任务：")
    print("   python -m src.daily_once")
    print("\n4. 对比结果：")
    print("   检查新旧交易记录和净值的差异")
else:
    print("✓ 今日无数据，可以安全执行任务")
    print("\n建议操作：")
    print("1. 确认今天是交易日")
    print("2. 调整 .env 中的 DAILY_AI_CALLS_LIMIT")
    print("3. 执行：python -m src.daily_once")

print("\n=== 检查完成 ===")

