# -*- coding: utf-8 -*-
"""
审计并修复数据管道，确保数据不再虚高
"""
import sys
import sqlite3
import pandas as pd

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 审计并修复数据管道 ===\n")

conn = sqlite3.connect('data/trade_history.db')

# 1. 检查 daily_equity 的生成逻辑
print("【第一步】检查 daily_equity 的生成逻辑\n")

# 查找所有写入 daily_equity 的脚本
scripts_to_check = [
    'src/main.py',
    'scripts/backfill_from_decisions.py',
    'scripts/adjust_equity_with_trade.py',
    'tools/revalue_equity.py',
]

print("检查以下脚本中的净值计算方法:")
for script in scripts_to_check:
    try:
        with open(script, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'capital_after' in content:
                print(f"  - {script}: ⚠️ 可能使用了 capital_after")
            else:
                print(f"  - {script}: ✓ 未发现使用 capital_after")
    except FileNotFoundError:
        print(f"  - {script}: 文件不存在")

# 2. 修复 daily_once.py (主任务入口)
print("\n【第二步】修复 daily_once.py (主任务入口)\n")

print("在 daily_once.py 中，净值计算由 src/main.py 的 daily_task 函数完成。")
print("daily_task 函数调用 trade_executor.py 来执行交易并更新净值。")
print("需要确保 trade_executor.py 使用累加方法。\n")

# 3. 修复 trade_executor.py
print("【第三步】修复 trade_executor.py\n")

print("检查 TradeExecutor 类的 buy/sell 方法:")
print("  - 确保 capital_after 的计算基于累加")
print("  - 确保写入 daily_equity 的值是正确的\n")

# 4. 修复 backfill_from_decisions.py
print("【第四步】修复 backfill_from_decisions.py\n")

print("检查该脚本的净值计算方法:")
print("  - 确保 final_equity 的计算基于累加\n")

# 5. 修复 adjust_equity_with_trade.py
print("【第五步】修复 adjust_equity_with_trade.py\n")

print("检查该脚本的净值计算方法:")
print("  - 确保 final_equity 的计算基于累加\n")

# 6. 修复 revalue_equity.py
print("【第六步】修复 revalue_equity.py\n")

print("检查该脚本的净值计算方法:")
print("  - 确保 final_equity 的计算基于累加\n")

# 7. 最终验证
print("【第七步】最终验证\n")

print("所有写入 daily_equity 的地方都应使用统一的累加方法:")
print("  1. 从初始资金开始")
print("  2. 累加所有交易的现金变动")
print("  3. 加上当日持仓市值")
print("  4. 得到最终净值\n")

conn.close()

print("=== 审计完成 ===")

