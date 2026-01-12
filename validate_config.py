# -*- coding: utf-8 -*-
"""
验证配置文件的正确性
执行：python validate_config.py
"""
import sys
import os
import yaml
import pandas as pd

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 配置验证 ===\n")

# 1. 检查 config.yaml
print("1. 检查 config.yaml:")
try:
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    strategy = config.get('strategy', {})
    
    # 验证风控参数
    checks = {
        'hard_stop_loss_pct': (0.08, '强制止损'),
        'quick_take_profit_trigger': (0.10, '快速止盈触发'),
        'quick_take_profit_sell_ratio': (0.5, '止盈卖出比例'),
        'enable_trailing_stop': (True, '跟踪止损开关'),
        'trailing_stop_pct': (0.05, '跟踪止损幅度'),
        'trailing_step_pct': (0.01, '跟踪止损步长'),
    }
    
    all_ok = True
    for key, (expected, desc) in checks.items():
        actual = strategy.get(key)
        if actual == expected:
            print(f"   ✓ {desc}: {actual}")
        else:
            print(f"   ✗ {desc}: {actual} (期望: {expected})")
            all_ok = False
    
    # 验证仓位参数
    pos_checks = {
        'enable_dynamic_position': (True, '动态仓位'),
        'base_position_pct': (0.15, '基础仓位'),
        'min_position_pct': (0.05, '最小仓位'),
        'max_position_pct': (0.25, '最大仓位'),
    }
    
    for key, (expected, desc) in pos_checks.items():
        actual = strategy.get(key)
        if actual == expected:
            print(f"   ✓ {desc}: {actual}")
        else:
            print(f"   ✗ {desc}: {actual} (期望: {expected})")
            all_ok = False
    
    if all_ok:
        print("\n   ✅ config.yaml 配置正确")
    else:
        print("\n   ⚠️ config.yaml 部分配置不符合预期")
        
except Exception as e:
    print(f"   ✗ 读取失败: {e}")

# 2. 检查 .env 文件
print("\n2. 检查 .env 文件:")
if os.path.exists('.env'):
    print("   ✓ .env 文件存在")
    
    # 读取并验证关键配置
    from dotenv import load_dotenv
    load_dotenv()
    
    etf_list = os.getenv('ETF_LIST', '')
    if etf_list:
        codes = [c.strip() for c in etf_list.split(',')]
        print(f"   ✓ ETF_LIST: {len(codes)} 只标的")
        
        # 验证新增ETF是否在列表中
        new_etfs = ['512290', '513520', '510580', '512680', '515030', '512170', '159605']
        missing = [c for c in new_etfs if c not in codes]
        if missing:
            print(f"   ⚠️ 缺少新增ETF: {', '.join(missing)}")
        else:
            print(f"   ✓ 所有新增ETF已配置")
    else:
        print("   ⚠️ ETF_LIST 未配置")
    
    # 检查其他关键配置
    key_configs = {
        'STRATEGY_MODE': 'AGGRESSIVE',
        'ENABLE_DYNAMIC_POSITION': 'true',
        'HARD_STOP_LOSS_PCT': '0.08',
        'DAILY_AI_CALLS_LIMIT': '8',
    }
    
    for key, expected in key_configs.items():
        actual = os.getenv(key, '')
        if actual.lower() == str(expected).lower():
            print(f"   ✓ {key}: {actual}")
        else:
            print(f"   ⚠️ {key}: {actual} (建议: {expected})")
            
else:
    print("   ✗ .env 文件不存在")
    print("   提示：请根据 env_config.txt 创建 .env 文件")

# 3. 检查数据库
print("\n3. 检查数据库:")
db_path = 'data/trade_history.db'
if os.path.exists(db_path):
    print(f"   ✓ {db_path} 存在")
    
    import sqlite3
    conn = sqlite3.connect(db_path)
    
    # 检查表
    tables = pd.read_sql_query(
        "SELECT name FROM sqlite_master WHERE type='table'",
        conn
    )
    print(f"   ✓ 数据表: {', '.join(tables['name'].tolist())}")
    
    # 检查交易记录数
    trades_count = pd.read_sql_query("SELECT COUNT(*) as cnt FROM trades", conn).iloc[0]['cnt']
    print(f"   ✓ 交易记录: {trades_count} 笔")
    
    # 检查净值记录数
    equity_count = pd.read_sql_query("SELECT COUNT(*) as cnt FROM daily_equity", conn).iloc[0]['cnt']
    print(f"   ✓ 净值记录: {equity_count} 天")
    
    conn.close()
else:
    print(f"   ⚠️ {db_path} 不存在")

# 4. 检查ETF数据
print("\n4. 检查ETF数据:")
etf_db_path = 'data/etf_data.db'
if os.path.exists(etf_db_path):
    print(f"   ✓ {etf_db_path} 存在")
    
    import sqlite3
    import pandas as pd
    conn = sqlite3.connect(etf_db_path)
    
    tables = pd.read_sql_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'etf_%'",
        conn
    )
    etf_codes = [t.replace('etf_', '') for t in tables['name'].tolist()]
    print(f"   ✓ 已有数据: {len(etf_codes)} 只ETF")
    
    # 检查新增ETF
    new_etfs = ['512290', '513520', '510580', '512680', '515030', '512170', '159605']
    missing = [c for c in new_etfs if c not in etf_codes]
    if missing:
        print(f"   ⚠️ 需要拉取数据: {', '.join(missing)}")
        print(f"   提示：运行 python fetch_new_etfs.py")
    else:
        print(f"   ✓ 所有新增ETF数据已就绪")
    
    conn.close()
else:
    print(f"   ⚠️ {etf_db_path} 不存在")

print("\n=== 验证完成 ===")

