# -*- coding: utf-8 -*-
"""
Qlib TopK 择时（脚本版）
- 读取 .env 中 ETF_LIST、QLIB_DIR、QLIB_REGION
- 初始化 Qlib provider（data/qlib/cn_etf）
- 基于最近 lookback 个自然日的收盘价，做简易动量 TopK 选择：
  ret = close[today] / close[first] - 1
  选择 TopK 作为买入候选，其余作为卖出候选
- 打印结果，并可将“今日信号”写为 JSON（可供后续集成使用）

用法（在 uv 环境）：
  uv run python -m scripts.qlib_today_topk --k 2 --lookback 60 --write-json
  # 或使用默认：K=2, lookback=60

注意：
- 需要在 uv 环境安装与 Qlib 兼容的依赖（numpy/pandas 1.x）：
    uv add "numpy==1.24.4" "pandas==1.5.3" pyqlib
- 并确保已构建 provider：data/qlib/cn_etf
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv


def read_env_list(key: str, default: list[str]) -> list[str]:
    val = os.getenv(key, "").strip()
    if not val:
        return default
    items = [x.strip() for x in val.split(",") if x.strip()]
    return items or default


def compute_topk(etfs: list[str], provider_uri: str, region: str, lookback: int, k: int):
    import qlib
    from qlib.data import D

    qlib.init(provider_uri=provider_uri, region=region)

    end = date.today()
    start = end - timedelta(days=max(lookback * 2, lookback + 30))  # 放大窗口以覆盖非交易日

    # 读取 close 特征
    df = D.features(etfs, ["$close"], start_time=str(start), end_time=str(end))
    if df is None or df.empty:
        return None, None, None
    df = df.dropna()
    if df.empty:
        return None, None, None

    # MultiIndex: (datetime, instrument)
    last_day = df.index.get_level_values(0).max()
    # 找到过去 lookback 窗的首日（按数据可用性）
    dates = sorted(df.index.get_level_values(0).unique())
    # 选最近 lookback 个“有数据”的交易日
    if len(dates) < 2:
        return None, None, None
    tail = dates[-lookback:] if len(dates) >= lookback else dates
    first_day = tail[0]

    today_close = df.xs(last_day, level=0)["$close"]
    base_close = df.xs(first_day, level=0)["$close"]

    # 仅保留今天和首日都有数据的标的
    common = today_close.index.intersection(base_close.index)
    today_close = today_close.loc[common]
    base_close = base_close.loc[common]
    if today_close.empty:
        return None, None, None

    ret = (today_close / base_close - 1.0).sort_values(ascending=False)
    top = ret.head(k)
    sells = [c for c in ret.index if c not in top.index]
    return last_day, top, sells


def main():
    load_dotenv(override=True)

    parser = argparse.ArgumentParser(description="Qlib TopK 择时（脚本版）")
    parser.add_argument("--k", type=int, default=int(os.getenv("QLIB_TOPK_K", "2")), help="TopK 数")
    parser.add_argument(
        "--lookback", type=int, default=int(os.getenv("QLIB_TOPK_LOOKBACK", "60")), help="动量回看窗口（自然日）"
    )
    parser.add_argument("--provider", type=str, default=os.getenv("QLIB_DIR", "data/qlib/cn_etf"))
    parser.add_argument("--region", type=str, default=os.getenv("QLIB_REGION", "cn"))
    parser.add_argument("--write-json", action="store_true", help="将今日信号写入 decisions/qlib_topk_YYYYMMDD.json")
    args = parser.parse_args()

    default_etfs = ["510050", "159915", "510300"]
    etfs = read_env_list("ETF_LIST", default_etfs)

    provider_uri = os.path.abspath(args.provider)
    region = args.region
    lookback = int(args.lookback)
    k = max(1, int(args.k))

    last_day, top, sells = compute_topk(etfs, provider_uri, region, lookback, k)
    if last_day is None or top is None:
        print("⚠️ 无法从 Qlib provider 读取足够数据，请检查 provider_uri 与数据是否存在:", provider_uri)
        return 1

    print(f"日期: {pd.to_datetime(last_day).date()}  provider: {provider_uri}")
    print(f"TopK({k}) by momentum (lookback={lookback}d):")
    for code, r in top.items():
        print(f" - {code}: {r*100:.2f}%")
    print("Sell candidates:", ", ".join(sells) if sells else "(none)")

    if args.write_json:
        decisions = []
        # 生成买入建议
        for code, r in top.items():
            decisions.append({
                "date": pd.to_datetime(last_day).strftime("%Y-%m-%d") + " 15:00:00",
                "etf_code": str(code),
                "decision": "buy",
                "confidence": 0.7,
                "reasoning": f"Qlib TopK (lookback={lookback}d, ret={r*100:.2f}%)",
            })
        # 生成卖出建议（仅作为候选，谨慎使用）
        for code in sells:
            decisions.append({
                "date": pd.to_datetime(last_day).strftime("%Y-%m-%d") + " 15:00:00",
                "etf_code": str(code),
                "decision": "sell",
                "confidence": 0.6,
                "reasoning": f"Qlib 非 TopK (lookback={lookback}d)",
            })
        out_dir = Path("decisions"); out_dir.mkdir(parents=True, exist_ok=True)
        out_fp = out_dir / f"qlib_topk_{pd.to_datetime(last_day).strftime('%Y%m%d')}.json"
        with open(out_fp, "w", encoding="utf-8") as f:
            json.dump({"date": pd.to_datetime(last_day).strftime("%Y-%m-%d"), "decisions": decisions}, f, ensure_ascii=False, indent=2)
        print("已写入:", str(out_fp))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

