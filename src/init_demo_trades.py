# -*- coding: utf-8 -*-
"""
演示数据初始化脚本
用于在没有实际交易时，为前端展示生成示例交易数据

使用方法:
    python -m src.init_demo_trades
"""
import os
import sqlite3
from datetime import datetime, timedelta
from src.trade_executor import TradeExecutor


def init_demo_trades():
    """初始化演示交易数据"""
    
    executor = TradeExecutor(initial_capital=100000.0)
    
    # 模拟交易序列（时间间隔1天）
    base_date = datetime.now() - timedelta(days=10)
    
    trades = [
        {
            'date': (base_date + timedelta(days=0)).strftime("%Y-%m-%d %H:%M:%S"),
            'etf_code': '510050',
            'action': 'buy',
            'price': 2.45,
            'quantity': 8163.27,
            'value': 20000.0,
            'capital_after': 80000.0,
            'reasoning': '演示数据：MA20上穿MA60，买入沪深300'
        },
        {
            'date': (base_date + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
            'etf_code': '159915',
            'action': 'buy',
            'price': 1.22,
            'quantity': 16393.44,
            'value': 20000.0,
            'capital_after': 60000.0,
            'reasoning': '演示数据：创业板指数向上突破，买入创业板'
        },
        {
            'date': (base_date + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
            'etf_code': '510300',
            'action': 'buy',
            'price': 3.68,
            'quantity': 5434.78,
            'value': 20000.0,
            'capital_after': 40000.0,
            'reasoning': '演示数据：沪深300指数强势，买入沪深300'
        },
        {
            'date': (base_date + timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S"),
            'etf_code': '510050',
            'action': 'sell',
            'price': 2.52,
            'quantity': 8163.27,
            'value': 20571.44,
            'capital_after': 60571.44,
            'reasoning': '演示数据：获利了结，卖出沪深300'
        },
        {
            'date': (base_date + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
            'etf_code': '159915',
            'action': 'sell',
            'price': 1.25,
            'quantity': 16393.44,
            'value': 20491.80,
            'capital_after': 81063.24,
            'reasoning': '演示数据：创业板回调，获利卖出'
        },
        {
            'date': (base_date + timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S"),
            'etf_code': '510300',
            'action': 'sell',
            'price': 3.75,
            'quantity': 5434.78,
            'value': 20380.43,
            'capital_after': 101443.67,
            'reasoning': '演示数据：止盈卖出，沪深300'
        },
        {
            'date': (base_date + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
            'etf_code': '510050',
            'action': 'buy',
            'price': 2.48,
            'quantity': 8056.45,
            'value': 20000.0,
            'capital_after': 81443.67,
            'reasoning': '演示数据：二次买入沪深300'
        },
        {
            'date': (base_date + timedelta(days=9)).strftime("%Y-%m-%d %H:%M:%S"),
            'etf_code': '510050',
            'action': 'sell',
            'price': 2.55,
            'quantity': 8056.45,
            'value': 20544.05,
            'capital_after': 101987.72,
            'reasoning': '演示数据：最终获利卖出'
        },
    ]
    
    # 写入数据库
    db_path = executor.db_path
    conn = sqlite3.connect(db_path)
    try:
        # 清空现有交易（可选）
        # conn.execute("DELETE FROM trades")
        
        for trade in trades:
            conn.execute(
                """INSERT INTO trades (date, etf_code, action, price, quantity, value, capital_after, reasoning)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade['date'],
                    trade['etf_code'],
                    trade['action'],
                    trade['price'],
                    trade['quantity'],
                    trade['value'],
                    trade['capital_after'],
                    trade['reasoning']
                )
            )
        conn.commit()
        print(f"✅ 成功插入 {len(trades)} 条演示交易数据")
        print(f"📊 数据库路径: {db_path}")
        print(f"💰 最终账户资产: {trades[-1]['capital_after']:.2f} 元")
        
    except Exception as e:
        print(f"❌ 插入数据失败: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_demo_trades()


