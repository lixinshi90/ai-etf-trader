# -*- coding: utf-8 -*-
"""
基于 out/*.csv 生成绩效摘要页（HTML）与收益曲线图片。
用法：
  uv run python scripts/generate_perf_summary.py
依赖：matplotlib、pandas、numpy（已在项目依赖中）
输出：
  out/REPORT_PERF_SUMMARY.html
  out/equity_curve.png
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUT = os.path.join(ROOT, 'out')
REPORT = os.path.join(OUT, 'REPORT_PERF_SUMMARY.html')

os.makedirs(OUT, exist_ok=True)

def fmt_pct(x):
    try:
        return f'{float(x):.2f}%'
    except Exception:
        return '--'


def load_csv():
    deq = None
    trades = None
    # 找最近生成的 daily_equity_from_*.csv
    cands = sorted([f for f in os.listdir(OUT) if f.startswith('daily_equity_from_') and f.endswith('.csv')])
    if cands:
        deq = pd.read_csv(os.path.join(OUT, cands[-1]))
    # 找 trades_from_*.csv
    tcands = sorted([f for f in os.listdir(OUT) if f.startswith('trades_from_') and f.endswith('.csv')])
    if tcands:
        trades = pd.read_csv(os.path.join(OUT, tcands[-1]))
    snap_fp = os.path.join(OUT, 'portfolio_snapshot.csv')
    snap_df = pd.read_csv(snap_fp) if os.path.exists(snap_fp) else pd.DataFrame()
    return deq, trades, snap_df


def compute_kpis(deq: pd.DataFrame | None, trades: pd.DataFrame | None) -> dict:
    k = {'total_trades': 0, 'buy_count': 0, 'sell_count': 0, 'win_rate': np.nan, 'total_return': np.nan, 'annualized': np.nan, 'mdd': np.nan}
    if trades is not None and not trades.empty:
        t = trades.copy()
        t['action'] = t['action'].astype(str).str.lower()
        k['buy_count'] = int((t['action']=='buy').sum())
        k['sell_count'] = int((t['action']=='sell').sum())
        k['total_trades'] = k['buy_count'] + k['sell_count']
        # 胜率：卖出盈利/卖出次数
        try:
            t['profit'] = t.apply(lambda r: float(r['value']) if str(r['action']).lower()=='sell' else -float(r['value']), axis=1)
            sells = t[t['action']=='sell']
            if not sells.empty:
                k['win_rate'] = 100.0 * (sells['profit'] > 0).mean()
        except Exception:
            pass
    if deq is not None and not deq.empty:
        d = deq.copy()
        try:
            d['date'] = pd.to_datetime(d['date'])
        except Exception:
            pass
        try:
            v = d['equity'].astype(float).values
            if len(v) >= 2:
                total_ret = (v[-1]-v[0])/v[0]
                days = max((d['date'].iloc[-1]-d['date'].iloc[0]).days, 1)
                ann = total_ret * (365.0/days)
                peak = np.maximum.accumulate(v)
                dd = (v - peak) / peak
                k['total_return'] = 100.0 * total_ret
                k['annualized'] = 100.0 * ann
                k['mdd'] = 100.0 * float(dd.min())
        except Exception:
            pass
    return k


def plot_equity(deq: pd.DataFrame | None, out_png: str):
    if deq is None or deq.empty:
        return
    d = deq.copy()
    try:
        d['date'] = pd.to_datetime(d['date'])
    except Exception:
        pass
    plt.figure(figsize=(9,4))
    try:
        plt.plot(d['date'], d['equity'], label='Equity')
    except Exception:
        plt.plot(d.index, d['equity'], label='Equity')
    plt.title('Equity Curve')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()


def trade_distribution(trades: pd.DataFrame | None):
    if trades is None or trades.empty:
        return None
    t = trades.copy()
    try:
        t['date'] = pd.to_datetime(t['date'])
        t['d'] = t['date'].dt.date
    except Exception:
        t['d'] = t['date']
    daily = t.groupby('d')['action'].value_counts().unstack(fill_value=0)
    # 确保有 buy/sell 两列
    if 'buy' not in daily.columns:
        daily['buy'] = 0
    if 'sell' not in daily.columns:
        daily['sell'] = 0
    return daily.reset_index().sort_values('d')


def build_html(deq, trades, snap, kpis):
    eq_png = os.path.join(OUT, 'equity_curve.png')
    plot_equity(deq, eq_png)
    html = []
    html.append('<html><head><meta charset="utf-8"><title>绩效摘要</title></head><body>')
    html.append('<h2>绩效摘要（近一月）</h2>')
    html.append('<h3>KPI</h3>')
    html.append('<table border="1" cellpadding="6" cellspacing="0">')
    rows = [
        ('总交易次数', kpis.get('total_trades', 0)),
        ('买入次数', kpis.get('buy_count', 0)),
        ('卖出次数', kpis.get('sell_count', 0)),
        ('胜率', fmt_pct(kpis.get('win_rate'))),
        ('总收益率', fmt_pct(kpis.get('total_return'))),
        ('年化收益率', fmt_pct(kpis.get('annualized'))),
        ('最大回撤', fmt_pct(kpis.get('mdd'))),
    ]
    for k, v in rows:
        html.append(f'<tr><td>{k}</td><td>{v}</td></tr>')
    html.append('</table>')
    html.append('<h3>收益曲线</h3>')
    if os.path.exists(eq_png):
        html.append(f'<img src="equity_curve.png" width="800"/>')
    else:
        html.append('<p>暂无曲线</p>')
    html.append('<h3>交易分布（按日）</h3>')
    dist = trade_distribution(trades)
    if dist is not None and not dist.empty:
        html.append('<table border="1" cellpadding="6" cellspacing="0"><tr><th>日期</th><th>买入</th><th>卖出</th></tr>')
        for _, r in dist.iterrows():
            buys = int(r.get('buy',0)); sells = int(r.get('sell',0))
            html.append(f'<tr><td>{r["d"]}</td><td>{buys}</td><td>{sells}</td></tr>')
        html.append('</table>')
    else:
        html.append('<p>暂无交易</p>')
    html.append('<h3>当前持仓</h3>')
    if snap is not None and not snap.empty:
        html.append('<table border="1" cellpadding="6" cellspacing="0"><tr><th>代码</th><th>数量</th><th>价格</th><th>市值</th></tr>')
        for _, r in snap.iterrows():
            try:
                html.append(f'<tr><td>{r["code"]}</td><td>{float(r["qty"]):.2f}</td><td>{float(r["px"]):.4f}</td><td>{float(r["value"]):.2f}</td></tr>')
            except Exception:
                html.append(f'<tr><td>{r.get("code","-")}</td><td>{r.get("qty","-")}</td><td>{r.get("px","-")}</td><td>{r.get("value","-")}</td></tr>')
        html.append('</table>')
    else:
        html.append('<p>无持仓</p>')
    html.append('</body></html>')
    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html))
    print('报告已生成 ->', REPORT)


if __name__ == '__main__':
    deq, trades, snap = load_csv()
    kpis = compute_kpis(deq, trades)
    build_html(deq, trades, snap, kpis)

