# -*- coding: utf-8 -*-
"""
策略性能分析脚本
功能：
1. 分析合规交易数据，找出收益为负的根源。
2. 统计约束触发次数、交易成本占比等关键指标。
3. 评估卖出时机，为策略优化提供数据支持。

用法：
  uv run python scripts/analyze_strategy_performance.py
"""
import os
import pandas as pd
import yaml

# --- Paths and Config ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")
TRADES_CSV = os.path.join(ROOT, 'out', 'resimulated_trades_fully_compliant.csv')

# Load configuration
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# --- Analysis Functions ---
def analyze_constraint_impact(df: pd.DataFrame):
    """分析仓位约束的影响"""
    total_trades = len(df)
    constrained_trades = df[df['constraint_triggered'] == 1]
    num_constrained = len(constrained_trades)
    
    print("--- 1. 约束影响分析 ---")
    if total_trades > 0:
        pct_constrained = (num_constrained / total_trades) * 100
        print(f"总交易次数: {total_trades}")
        print(f"触发约束的交易次数: {num_constrained} ({pct_constrained:.2f}%)")
        if pct_constrained > 30:
            print("结论: 超过30%的交易被仓位/现金约束限制，表明策略的交易意图过于激进，频繁触及风控上限。这可能导致错失部分收益，但也保证了风险可控。")
        else:
            print("结论: 约束触发比例在合理范围内，风控机制正常运作，未过度限制策略。")
    else:
        print("无交易数据可供分析。")
    print("\n")

def analyze_cost_impact(df: pd.DataFrame):
    """分析交易成本的影响"""
    total_cost = df['trade_cost'].sum()
    total_volume = df['value'].sum()
    
    print("--- 2. 交易成本分析 ---")
    if total_volume > 0:
        cost_ratio = (total_cost / total_volume) * 100
        print(f"总交易额: {total_volume:,.2f}")
        print(f"总交易成本: {total_cost:,.2f}")
        print(f"成本占比: {cost_ratio:.4f}%")
        
        # 从配置加载成本参数用于对比
        costs = config.get('costs', {})
        buy_cost_pct = (costs.get('buy_slippage', 0) + costs.get('buy_commission', 0)) * 100
        sell_cost_pct = (costs.get('sell_slippage', 0) + costs.get('sell_commission', 0) + costs.get('sell_tax', 0)) * 100
        print(f"(参考) 买入成本率: {buy_cost_pct:.4f}%, 卖出成本率: {sell_cost_pct:.4f}%")

        if cost_ratio > 1.5:
            print("结论: 交易成本占比偏高(>1.5%)，显著侵蚀了策略利润。建议优化方向：降低交易频率、选择低成本标的、或确认滑点/佣金参数是否符合实际。")
        else:
            print("结论: 交易成本在可接受范围内。")
    else:
        print("无交易数据可供分析。")
    print("\n")

def analyze_sell_timing(df: pd.DataFrame):
    """分析卖出时机"""
    sells = df[df['action'] == 'sell'].copy()
    buys = df[df['action'] == 'buy'].copy()

    print("--- 3. 卖出时机分析 ---")
    if sells.empty or buys.empty:
        print("无完整的买卖交易对，无法分析卖出时机。")
        return

    # 这是一个简化的匹配逻辑：为每笔卖出找到最近的一次买入
    sells['holding_period_days'] = 0
    sells['return_pct'] = 0.0

    for i, sell_trade in sells.iterrows():
        # 找到这笔卖出之前，相同代码的最后一笔买入
        relevant_buys = buys[(buys['etf_code'] == sell_trade['etf_code']) & (buys['date'] < sell_trade['date'])]
        if not relevant_buys.empty:
            last_buy = relevant_buys.iloc[-1]
            
            # 计算持有期
            holding_period = pd.to_datetime(sell_trade['date']) - pd.to_datetime(last_buy['date'])
            sells.loc[i, 'holding_period_days'] = holding_period.days
            
            # 计算这笔交易的收益率
            trade_return = (sell_trade['price'] - last_buy['price']) / last_buy['price']
            sells.loc[i, 'return_pct'] = trade_return * 100

    avg_holding_period = sells['holding_period_days'].mean()
    avg_return = sells['return_pct'].mean()
    win_sells = sells[sells['return_pct'] > 0]
    loss_sells = sells[sells['return_pct'] <= 0]

    print(f"卖出交易总数: {len(sells)}")
    print(f"平均持仓天数: {avg_holding_period:.2f} 天")
    print(f"平均单笔收益率: {avg_return:.2f}%")
    if not win_sells.empty:
        print(f"盈利卖出平均收益率: {win_sells['return_pct'].mean():.2f}% (共 {len(win_sells)} 笔)")
    if not loss_sells.empty:
        print(f"亏损卖出平均收益率: {loss_sells['return_pct'].mean():.2f}% (共 {len(loss_sells)} 笔)")

    if avg_holding_period < 5:
        print("结论: 平均持仓周期较短(<5天)，策略偏向高频交易。若平均收益率不高，可能是频繁交易被成本侵蚀，或过早卖出导致错失趋势性机会。")
    else:
        print("结论: 平均持仓周期正常。若亏损笔数较多或亏损幅度大，应检查止损逻辑是否有效。")
    print("\n")

def main():
    """主执行函数"""
    if not os.path.exists(TRADES_CSV):
        print(f"Error: Compliant trades file not found at '{TRADES_CSV}'")
        return

    trades_df = pd.read_csv(TRADES_CSV)
    
    print(f"======== 策略性能分析报告 ({pd.Timestamp.now().strftime('%Y-%m-%d')}) ========")
    analyze_constraint_impact(trades_df)
    analyze_cost_impact(trades_df)
    analyze_sell_timing(trades_df)
    print("==================== 分析结束 ====================")

if __name__ == "__main__":
    main()

