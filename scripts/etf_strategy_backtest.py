# -*- coding: utf-8 -*-
"""
ETF 策略回测脚本

功能：
- 对 ETF_LIST 中的每个标的，在指定历史时间段内运行指定的规则策略。
- 模拟交易过程，包括手续费和滑点。
- 计算并输出每个标的的绩效指标（总收益、年化收益、最大回撤、夏普比率、胜率）。
- 支持根据绩效筛选标的，并将结果输出到文件或直接更新 .env。

用法：
    # 回测 KDJ_MACD 策略
    python -m scripts.etf_strategy_backtest --strategy KDJ_MACD

    # 回测 AGGRESSIVE 策略，并根据年化收益筛选，将结果保存到 filtered_etf_list.txt
    python -m scripts.etf_strategy_backtest --strategy AGGRESSIVE --days 365 --filter-metric "年化收益(%)" --filter-threshold 10

    # 回测并直接更新 .env 文件（高风险）
    python -m scripts.etf_strategy_backtest --strategy AGGRESSIVE --filter-metric "夏普比率" --filter-threshold 0.5 --update-env

"""
import argparse
import os
import sys
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 将项目根目录添加到Python路径，以便导入src模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.main import get_rule_decision
from src.data_fetcher import _etf_db_path

class Backtester:
    """简化的向量化回测引擎"""
    def __init__(self, etf_code: str, strategy: str, params: dict, start_date: str, end_date: str):
        self.etf_code = etf_code
        self.strategy = strategy
        self.params = params
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = 100000
        self.cost_bps = 5  # 万分之5
        self.slippage_bps = 2 # 万分之2

    def _load_data(self) -> pd.DataFrame | None:
        """从数据库加载并准备数据"""
        try:
            conn = sqlite3.connect(_etf_db_path())
            df = pd.read_sql_query(f"SELECT * FROM etf_{self.etf_code}", conn)
            conn.close()

            date_col = next((c for c in ['日期', 'date'] if c in df.columns), None)
            if not date_col:
                return None
            
            df['date'] = pd.to_datetime(df[date_col])
            df = df.set_index('date')
            df = df[self.start_date:self.end_date]
            return df.sort_index()
        except Exception as e:
            print(f"加载 {self.etf_code} 数据失败: {e}")
            return None

    def run(self) -> dict | None:
        """执行回测并返回绩效"""
        df = self._load_data()
        if df is None or df.empty or len(df) < 20: # 数据太少无意义
            return None

        signals = []
        for i in range(20, len(df)):
            past_df = df.iloc[:i]
            decision = get_rule_decision(past_df, self.params, self.etf_code)
            signals.append(decision.get('decision', 'hold'))
        
        df = df.iloc[19:]
        signals.insert(0, 'hold')
        df['signal'] = signals

        df['position'] = df['signal'].replace({'buy': 1, 'sell': 0, 'hold': np.nan}).ffill().fillna(0)
        df['trade'] = df['position'].diff().fillna(0)

        df['cash'] = self.initial_capital
        df['holdings'] = 0.0
        df['equity'] = self.initial_capital

        position = 0
        cash = self.initial_capital
        
        for i in range(1, len(df)):
            open_price = df['开盘'].iloc[i]
            close_price = df['收盘'].iloc[i]

            if df['trade'].iloc[i] == 1 and position == 0: # 买入
                price = open_price * (1 + self.slippage_bps / 10000)
                cost = price * (self.cost_bps / 10000)
                position = cash / (price + cost)
                cash = 0
            elif df['trade'].iloc[i] == -1 and position > 0: # 卖出
                price = open_price * (1 - self.slippage_bps / 10000)
                cost = price * (self.cost_bps / 10000)
                cash = position * (price - cost)
                position = 0

            df.loc[df.index[i], 'cash'] = cash
            df.loc[df.index[i], 'holdings'] = position * close_price
            df.loc[df.index[i], 'equity'] = cash + (position * close_price)

        return self._calculate_performance(df)

    def _calculate_performance(self, df: pd.DataFrame) -> dict:
        equity_series = df['equity']
        total_return = (equity_series.iloc[-1] / equity_series.iloc[0] - 1) * 100
        
        days = (equity_series.index[-1] - equity_series.index[0]).days
        annual_return = ((1 + total_return / 100) ** (365.0 / days) - 1) * 100 if days > 0 else 0

        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100

        returns = equity_series.pct_change().dropna()
        sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0

        sell_trades = df[df['trade'] == -1]
        wins = 0
        if not sell_trades.empty:
            buy_trades = df[df['trade'] == 1]
            for sell_idx, sell_trade in sell_trades.iterrows():
                relevant_buys = buy_trades[buy_trades.index < sell_idx]
                if not relevant_buys.empty:
                    last_buy_idx = relevant_buys.index[-1]
                    # 确保这次卖出是对应最近一次买入之后
                    if not sell_trades[sell_trades.index < sell_idx].empty and sell_trades[sell_trades.index < sell_idx].index[-1] > last_buy_idx:
                        continue
                    buy_price = df.loc[last_buy_idx]['开盘']
                    if sell_trade['开盘'] > buy_price:
                        wins += 1
            win_rate = (wins / len(sell_trades)) * 100 if len(sell_trades) > 0 else 0
        else:
            win_rate = 0

        return {
            'ETF': self.etf_code,
            '策略': self.strategy,
            '总收益(%)': round(total_return, 2),
            '年化收益(%)': round(annual_return, 2),
            '最大回撤(%)': round(max_drawdown, 2),
            '夏普比率': round(sharpe_ratio, 2),
            '胜率(%)': round(win_rate, 2),
            '交易次数': len(sell_trades)
        }

def main():
    parser = argparse.ArgumentParser(description='ETF 策略回测脚本')
    parser.add_argument('--strategy', type=str, required=True, help='要回测的策略模式 (例如 KDJ_MACD, AGGRESSIVE)')
    parser.add_argument('--days', type=int, default=365, help='回测历史天数')
    parser.add_argument('--filter-metric', type=str, help='用于筛选标的池的绩效指标 (例如 "夏普比率", "年化收益(%)")')
    parser.add_argument('--filter-threshold', type=float, default=0.0, help='筛选指标的最小阈值')
    parser.add_argument('--update-env', action='store_true', help='直接更新 .env 文件中的 ETF_LIST (高风险操作)')
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    etf_list_str = os.getenv("ETF_LIST", "510050,510300,159915")
    etf_list = [code.strip() for code in etf_list_str.split(',')]

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')

    print(f"--- 开始回测 ---")
    print(f"策略: {args.strategy}")
    print(f"标的: {', '.join(etf_list)}")
    print(f"周期: {start_date} to {end_date}")
    print("-" * 20)

    results = []
    for etf_code in etf_list:
        params = {
            "mode": args.strategy,
            "kdj_low": int(os.getenv("KDJ_LOW", "20")),
            "rsi_low": int(os.getenv("RSI_LOW", "10")),
            "rsi_high": int(os.getenv("RSI_HIGH", "95")),
            "breakout_n": int(os.getenv("BREAKOUT_N", "20")),
        }
        backtester = Backtester(etf_code, args.strategy, params, start_date, end_date)
        performance = backtester.run()
        if performance:
            results.append(performance)
            print(f"✅ {etf_code} 回测完成")
        else:
            print(f"❌ {etf_code} 回测失败或无数据")

    if results:
        results_df = pd.DataFrame(results)
        print("\n--- 回测绩效总结 ---")
        print(results_df.to_string(index=False))

        if args.filter_metric:
            if args.filter_metric not in results_df.columns:
                print(f"\n错误: 指标 '{args.filter_metric}' 不存在。可用指标: {results_df.columns.tolist()}")
                return

            filtered_df = results_df[results_df[args.filter_metric] >= args.filter_threshold]
            filtered_etfs = filtered_df['ETF'].tolist()

            print(f"\n--- 筛选结果 (基于 {args.filter_metric} >= {args.filter_threshold}) ---")
            print(f"筛选出 {len(filtered_etfs)} 个标的: {', '.join(filtered_etfs)}")

            if args.update_env:
                env_path = os.path.join(project_root, '.env')
                if not os.path.exists(env_path):
                    print(f"警告: .env 文件未找到，无法更新。")
                else:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    new_lines = []
                    found = False
                    for line in lines:
                        if line.strip().startswith('ETF_LIST='):
                            new_lines.append(f"ETF_LIST={','.join(filtered_etfs)}\n")
                            found = True
                        else:
                            new_lines.append(line)
                    
                    if not found:
                        new_lines.append(f"\nETF_LIST={','.join(filtered_etfs)}\n")

                    with open(env_path, 'w', encoding='utf-8') as f:
                        f.writelines(new_lines)
                    print(f"✅ .env 文件中的 ETF_LIST 已更新。")
            else:
                output_path = os.path.join(project_root, 'filtered_etf_list.txt')
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(','.join(filtered_etfs))
                print(f"\n✅ 筛选结果已保存到: {output_path}")

if __name__ == "__main__":
    main()
