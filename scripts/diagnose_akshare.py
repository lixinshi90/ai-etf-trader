# -*- coding: utf-8 -*-
"""
诊断 akshare 实时 ETF 数据源的连通性。

功能:
- 应用与项目中相同的浏览器头和重试机制。
- 依次尝试 Eastmoney, Sina, 10jqka 三个数据源。
- 报告每个源的连接状态和获取到的数据行数。

用法 (在 uv 环境中):
  uv run python -m scripts.diagnose_akshare
"""
from __future__ import annotations

import sys
import os

# 确保能从 src 导入
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    try:
        import akshare as ak
        from src.data_fetcher import _configure_ak_session
        import pandas as pd
    except ImportError as e:
        print(f"❌ 无法导入所需模块: {e}")
        print("请确保在 uv 环境中，并已安装 akshare")
        return

    def _pref(code: str) -> str:
        code = str(code)
        if code.startswith(('5', '6')):
            return f"sh{code}"
        return f"sz{code}"

    def _pick(df: 'pd.DataFrame', *cands):
        for c in cands:
            if c in df.columns:
                return c
        return None

    print("1. 配置请求头与重试机制...")
    _configure_ak_session()
    print("   ✅ 配置完成。")

    # 定义要检查的数据源函数名（基于当前可用函数）
    sources_to_check = [
        ("Eastmoney (东方财富) 实时", "fund_etf_spot_em"),
        ("同花顺(THS) 实时", "fund_etf_spot_ths"),
        ("ETF 历史(日线) EM", "fund_etf_hist_em"),
        ("ETF 历史(日线) Sina", "fund_etf_hist_sina"),
    ]

    for name, func_name in sources_to_check:
        print(f"\n2. 正在测试: {name}")
        
        if not hasattr(ak, func_name):
            print(f"   ⚠️ 函数 '{func_name}' 在当前 akshare 版本中不存在，跳过。")
            continue

        try:
            func = getattr(ak, func_name)
            # 调用各自的正确签名
            if func_name == "fund_etf_hist_em":
                df = func(symbol="510050", period="daily", start_date="20240101", end_date="20241231")
            elif func_name == "fund_etf_hist_sina":
                df = func(symbol=_pref("510050"))
            else:
                df = func()

            if df is not None and not df.empty:
                print(f"   ✅ 连接成功！获取到 {len(df)} 行数据。")
                # 预览：spot 源显示 code/name/price；hist 源显示 date/close
                if func_name in ("fund_etf_spot_em", "fund_etf_spot_ths"):
                    code_c = _pick(df, "代码", "symbol", "代码code", "code")
                    name_c = _pick(df, "名称", "name")
                    price_c = _pick(df, "最新价", "最新价(元)", "现价", "最新", "price")
                    if code_c and price_c:
                        prev = df[[c for c in [code_c, name_c, price_c] if c]].head(3).copy()
                        prev.columns = ["code" if c==code_c else ("name" if c==name_c else ("price" if c==price_c else c)) for c in prev.columns]
                        print("      前3行数据预览:")
                        print(prev.to_string(index=False))
                    else:
                        print("      (无法定位标准列，显示列名)")
                        print("      列: ", ", ".join(map(str, df.columns[:10])))
                else:
                    date_c = _pick(df, "日期", "date", "Date")
                    close_c = _pick(df, "收盘", "收盘价", "close", "Close")
                    if date_c and close_c:
                        prev = df[[date_c, close_c]].head(3).copy()
                        prev.columns = ["date", "close"]
                        print("      前3行数据预览:")
                        print(prev.to_string(index=False))
                    else:
                        print("      (无法定位日期/收盘列，显示列名)")
                        print("      列: ", ", ".join(map(str, df.columns[:10])))
            else:
                print("   ⚠️ 连接成功，但未返回数据。")
        except Exception as e:
            print(f"   ❌ 连接失败: {type(e).__name__} - {e}")

    print("\n🏁 诊断完成。")
    print("\n💡 如果所有可用的源都失败，很可能是网络问题（如IP被风控）。请尝试切换网络（如手机热点）后重试。")
    print("💡 如果关键数据源函数不存在，请考虑升级 akshare: uv run pip install --upgrade akshare")

if __name__ == "__main__":
    main()
