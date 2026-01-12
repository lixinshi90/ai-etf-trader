# -*- coding: utf-8 -*-
"""
独立审计脚本（全量重仿真版）
功能：
1. 从配置文件加载参数，按时间顺序逐笔重放交易。
2. 对所有买入交易强制施加“现金约束”和“仓位约束”。
3. 输出完全合规的全新交易清单、每日净值曲线，以及每日绩效报告。
4. 增加结构化日志，记录重仿真过程。

用法：
  uv run python scripts/audit_financials.py
"""
from __future__ import annotations
import os
import sys
import sqlite3
import pandas as pd
import logging
import yaml
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- Constants and Configuration ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")

# Load configuration from YAML file
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

DB_TRADES = os.path.join(ROOT, 'data', 'trade_history.db')
DB_ETF = os.path.join(ROOT, 'data', 'etf_data.db')
OUT_DIR = os.path.join(ROOT, 'out')
LOG_DIR = os.path.join(ROOT, 'logs')
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# --- Parameters from Config ---
strategy_params = config.get('strategy', {})
INITIAL_CAPITAL = strategy_params.get('initial_capital', 100000.0)
MAX_POSITION_PCT = strategy_params.get('max_position_pct', 0.20)

cost_params = config.get('costs', {})
BUY_SLIPPAGE = cost_params.get('buy_slippage', 0.001)
BUY_COMMISSION = cost_params.get('buy_commission', 0.0005)
SELL_SLIPPAGE = cost_params.get('sell_slippage', 0.001)
SELL_COMMISSION = cost_params.get('sell_commission', 0.0005)
SELL_TAX = cost_params.get('sell_tax', 0.001)

# --- Logger Setup ---
log_file = os.path.join(LOG_DIR, f"resimulation_{datetime.now().strftime('%Y%m%d')}.log")
# Clear previous handlers
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ... (The rest of the script remains the same) ...

def get_etf_column_names(cursor: sqlite3.Cursor, table_name: str) -> tuple[str, str] | None:
    try:
        cursor.execute(f"SELECT 收盘, 日期 FROM {table_name} LIMIT 0")
        return '收盘', '日期'
    except sqlite3.OperationalError:
        try:
            cursor.execute(f"SELECT close, date FROM {table_name} LIMIT 0")
            return 'close', 'date'
        except sqlite3.OperationalError:
            return None

def resimulate_trade_history() -> pd.DataFrame | None:
    logging.info("Starting trade history re-simulation.")
    if not os.path.exists(DB_TRADES):
        logging.error(f"Trade database not found at {DB_TRADES}")
        return None
    conn = sqlite3.connect(DB_TRADES)
    try:
        original_trades = pd.read_sql_query("SELECT * FROM trades ORDER BY datetime(date)", conn)
    finally:
        conn.close()

    if original_trades.empty:
        logging.warning("No trades found in the database.")
        return None

    compliant_trades = []
    current_capital = INITIAL_CAPITAL
    holdings = {}
    logging.info(f"Initial capital set to: {INITIAL_CAPITAL:.2f}")

    for _, row in original_trades.iterrows():
        action = row['action']
        price = float(row['price'])
        original_value = float(row['value'])
        etf_code = row['etf_code']
        trade_date = row['date']

        new_row = row.to_dict()
        new_row['prev_cash'] = current_capital
        new_row['trade_pct'] = 0.0
        new_row['constraint_triggered'] = 0
        new_row['trade_cost'] = 0.0

        if action == 'buy':
            log_prefix = f"[{trade_date}][{etf_code}] BUY Intention: value={original_value:.2f}."
            
            max_buy_value_pos = current_capital * MAX_POSITION_PCT
            total_cost_rate = 1 + BUY_SLIPPAGE + BUY_COMMISSION
            max_buy_value_cash = current_capital / total_cost_rate

            buy_value = original_value
            triggered_reason = ""

            if buy_value > max_buy_value_pos:
                buy_value = max_buy_value_pos
                new_row['constraint_triggered'] = 1
                triggered_reason = f"Position constraint triggered ({MAX_POSITION_PCT*100}% of {current_capital:.2f})."
            
            if buy_value > max_buy_value_cash:
                buy_value = max_buy_value_cash
                new_row['constraint_triggered'] = 1
                triggered_reason = f"Cash constraint triggered (available: {current_capital:.2f})."

            if new_row['constraint_triggered']:
                logging.warning(f"{log_prefix} {triggered_reason} Adjusted value to {buy_value:.2f}.")
            else:
                logging.info(f"{log_prefix} Compliant. Executing as is.")

            buy_quantity = buy_value / price if price > 0 else 0

            if buy_quantity > 0:
                cost = buy_value * (BUY_SLIPPAGE + BUY_COMMISSION)
                current_capital -= (buy_value + cost)
                holdings[etf_code] = holdings.get(etf_code, 0) + buy_quantity
                
                new_row.update({
                    'value': buy_value, 'quantity': buy_quantity, 'capital_after': current_capital,
                    'trade_cost': cost, 'trade_pct': (buy_value / new_row['prev_cash']) * 100 if new_row['prev_cash'] > 0 else 0
                })
                compliant_trades.append(new_row)
            else:
                logging.error(f"{log_prefix} Trade value resulted in zero quantity. Skipping.")

        elif action == 'sell':
            original_qty = float(row['quantity'])
            available_qty = holdings.get(etf_code, 0)
            sell_quantity = min(original_qty, available_qty)
            log_prefix = f"[{trade_date}][{etf_code}] SELL Intention: qty={original_qty:.2f}."

            if sell_quantity < original_qty:
                logging.warning(f"{log_prefix} Available qty is {available_qty:.2f}. Adjusted sell qty to {sell_quantity:.2f}.")
            else:
                logging.info(f"{log_prefix} Executing as is.")

            if sell_quantity > 0:
                sell_value = sell_quantity * price
                cost = sell_value * (SELL_SLIPPAGE + SELL_COMMISSION + SELL_TAX)
                current_capital += (sell_value - cost)
                holdings[etf_code] -= sell_quantity

                new_row.update({
                    'value': sell_value, 'quantity': sell_quantity, 'capital_after': current_capital, 'trade_cost': cost
                })
                compliant_trades.append(new_row)

    logging.info("Re-simulation complete.")
    return pd.DataFrame(compliant_trades)

def generate_daily_reports(trades_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if trades_df is None or trades_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    
    df = trades_df.copy()
    df['date_only'] = pd.to_datetime(df['date']).dt.date
    
    daily_agg = df.groupby('date_only').agg(
        constraint_triggers=('constraint_triggered', 'sum'),
        cost_loss=('trade_cost', 'sum')
    ).reset_index()

    daily_cash = df.groupby('date_only')['capital_after'].last()
    all_dates = pd.to_datetime(sorted(daily_cash.index))
    
    report_data = []
    conn_etf = sqlite3.connect(DB_ETF)
    cursor_etf = conn_etf.cursor()
    try:
        for dt in all_dates:
            dt_date = dt.date()
            temp_df = df[df['date_only'] <= dt_date]
            
            positions = {}
            for _, trade in temp_df.iterrows():
                qty = trade['quantity'] if trade['action'] == 'buy' else -trade['quantity']
                positions[trade['etf_code']] = positions.get(trade['etf_code'], 0) + qty

            holdings_value = 0
            for code, qty in positions.items():
                if qty > 1e-9:
                    table_name = f'etf_{code}'
                    column_names = get_etf_column_names(cursor_etf, table_name)
                    if not column_names: continue
                    close_col, date_col = column_names
                    
                    query = f"SELECT {close_col} FROM {table_name} WHERE {date_col} <= ? ORDER BY {date_col} DESC LIMIT 1"
                    price_df = pd.read_sql_query(query, conn_etf, params=(dt.strftime('%Y-%m-%d'),))
                    
                    if not price_df.empty:
                        holdings_value += qty * price_df.iloc[0, 0]
            
            cash = daily_cash[dt_date]
            total_assets = cash + holdings_value
            report_data.append({'date': dt, 'cash': cash, 'holdings_value': holdings_value, 'total_assets': total_assets})
    finally:
        conn_etf.close()

    perf_df = pd.DataFrame(report_data).set_index('date')
    perf_df['daily_return_pct'] = (perf_df['total_assets'].pct_change() * 100).fillna(0)
    perf_df = perf_df.reset_index()
    perf_df['date_only'] = perf_df['date'].dt.date

    final_perf_df = pd.merge(perf_df, daily_agg, on='date_only', how='left').fillna(0)
    final_perf_df['date'] = final_perf_df['date'].dt.strftime('%Y-%m-%d')
    del final_perf_df['date_only']

    equity_df = final_perf_df[['date', 'total_assets']].rename(columns={'total_assets': 'equity'})

    return equity_df, final_perf_df

def main():
    logging.info("=== Starting Audit and Re-simulation Process ===")
    print('=== 1) 逐笔交易明细（全量重仿真）===')
    resimulated_trades = resimulate_trade_history()
    if resimulated_trades is None or resimulated_trades.empty:
        logging.warning("Trade re-simulation resulted in no compliant trades.")
        print('(无交易记录)')
    else:
        pd.set_option('display.max_rows', 100)
        print(resimulated_trades[['date', 'etf_code', 'action', 'price', 'quantity', 'value', 'capital_after', 'prev_cash', 'trade_pct', 'constraint_triggered']].to_string(index=False))
        buys = int((resimulated_trades['action']=='buy').sum())
        sells = int((resimulated_trades['action']=='sell').sum())
        max_buy_pct = float(pd.to_numeric(resimulated_trades.loc[resimulated_trades['action']=='buy','trade_pct'], errors='coerce').max() or 0)
        print(f"\nBuys: {buys}  Sells: {sells}  Max single BUY%: {max_buy_pct:.2f}%")
        resimulated_trades.to_csv(os.path.join(OUT_DIR, 'resimulated_trades_fully_compliant.csv'), index=False, encoding='utf-8-sig')
        logging.info(f"Saved {len(resimulated_trades)} compliant trades to out/resimulated_trades_fully_compliant.csv")
        print(f'保存 -> out/resimulated_trades_fully_compliant.csv')

    print('\n=== 2) 生成每日绩效与净值报告 ===')
    daily_equity, daily_perf = generate_daily_reports(resimulated_trades)
    
    if daily_equity.empty:
        logging.warning("Could not generate daily equity report.")
        print('(无法生成净值曲线)')
    else:
        print('\n--- 日终净值 ---')
        print(daily_equity.to_string(index=False))
        daily_equity.to_csv(os.path.join(OUT_DIR, 'resimulated_daily_equity.csv'), index=False, encoding='utf-8-sig')
        logging.info(f"Saved daily equity report with {len(daily_equity)} entries.")
        print(f'保存 -> out/resimulated_daily_equity.csv')

    if daily_perf.empty:
        logging.warning("Could not generate daily performance report.")
        print('(无法生成每日绩效)')
    else:
        print('\n--- 每日绩效 ---')
        print(daily_perf.to_string(index=False))
        daily_perf.to_csv(os.path.join(OUT_DIR, 'resimulated_daily_performance.csv'), index=False, encoding='utf-8-sig')
        logging.info(f"Saved daily performance report with {len(daily_perf)} entries.")
        print(f'保存 -> out/resimulated_daily_performance.csv')
    logging.info("=== Audit and Re-simulation Process Finished ===")

if __name__ == '__main__':
    main()
