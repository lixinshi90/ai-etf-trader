import pandas as pd
import numpy as np
import sys

def expand_trading_equity_to_calendar(csv_path: str,
                                     start=None,
                                     end=None) -> pd.DataFrame:
    """
    将交易日 equity 序列扩展为自然日 equity 序列（规则1：优先当日，否则向前对齐）
    返回 DataFrame: calendar_date, trading_date, equity
    """
    try:
        df = pd.read_csv(csv_path, parse_dates=["date"])
    except FileNotFoundError:
        print(f"Error: Input file not found at {csv_path}", file=sys.stderr)
        sys.exit(1)

    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    if df.empty:
        print(f"Error: Input file {csv_path} is empty or has no valid data.", file=sys.stderr)
        sys.exit(1)

    trading_days = pd.DatetimeIndex(df["date"])
    equity = pd.Series(df["equity"].to_numpy(), index=trading_days)

    # 确定自然日范围：默认用交易日首尾覆盖
    start = pd.to_datetime(start) if start is not None else trading_days.min()
    end = pd.to_datetime(end) if end is not None else trading_days.max()

    calendar_days = pd.date_range(start, end, freq="D")

    # 核心：向前对齐映射（当日是交易日则映射到当日）
    idx = trading_days.searchsorted(calendar_days, side="right") - 1

    # 边界：自然日早于第一交易日 -> idx=-1；这里置为 NaN
    trading_mapped = pd.Series(pd.NaT, index=calendar_days, dtype="datetime64[ns]")
    valid = idx >= 0
    trading_mapped.loc[valid] = trading_days[idx[valid]]

    out = pd.DataFrame({
        "calendar_date": calendar_days,
        "trading_date": trading_mapped.values,
    })

    # 把 equity 对齐进来
    out["equity"] = out["trading_date"].map(equity)

    return out

if __name__ == "__main__":
    input_file = "out/corrected_daily_equity.csv"
    output_file = "out/calendar_daily_equity.csv"

    print(f"Reading from {input_file}...")
    calendar_equity_df = expand_trading_equity_to_calendar(input_file)
    
    # 填充周末/节假日的 equity
    calendar_equity_df['equity'] = calendar_equity_df['equity'].ffill()

    calendar_equity_df.to_csv(output_file, index=False, date_format='%Y-%m-%d')
    print(f"Successfully created natural day equity file at {output_file}")

