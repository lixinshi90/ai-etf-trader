import pandas as pd
from pathlib import Path

CSV_PATH = Path("out/corrected_daily_equity.csv")
HOLDINGS_20251223 = Path("out/holdings_breakdown_2025-12-23.csv")

# From daily.log (2025-12-23): cash=52476.44
CASH_20251223 = 52476.44

# From daily.log (2025-12-24 equity-breakdown close):
CLOSE_20251224 = {
    "510300": 4.7570,
    "513500": 2.4550,
    "159928": 0.7990,
    "512040": 1.1470,
    "510880": 3.1650,
    "159915": 3.2120,
}


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")
    if not HOLDINGS_20251223.exists():
        raise FileNotFoundError(f"Holdings breakdown not found: {HOLDINGS_20251223}")

    h = pd.read_csv(HOLDINGS_20251223)
    if not {"code", "qty_asof"}.issubset(h.columns):
        raise ValueError("holdings_breakdown CSV must have columns: code, qty_asof")

    # No trade on 12/24 => qty stays same as of 12/23
    h["code"] = h["code"].astype(str)
    h["qty_asof"] = h["qty_asof"].astype(float)

    def get_px(code: str) -> float:
        if code not in CLOSE_20251224:
            raise KeyError(f"Missing 2025-12-24 close for code={code}")
        return float(CLOSE_20251224[code])

    h["close_20251224"] = h["code"].map(get_px)
    h["value_20251224"] = h["qty_asof"] * h["close_20251224"]

    holdings_20251224 = float(h["value_20251224"].sum())
    equity_20251224 = float(CASH_20251223 + holdings_20251224)

    # Append/override 2025-12-24 in corrected equity
    df = pd.read_csv(CSV_PATH)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    add_df = pd.DataFrame([{"date": "2025-12-24", "equity": equity_20251224}])
    out = pd.concat([df, add_df], ignore_index=True)
    out = out.drop_duplicates(subset=["date"], keep="last")
    out["_date_sort"] = pd.to_datetime(out["date"])
    out = out.sort_values("_date_sort").drop(columns=["_date_sort"])

    out.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")

    print("[ok] appended/updated 2025-12-24")
    print(f"cash_20251223={CASH_20251223:.2f}")
    print(f"holdings_20251224={holdings_20251224:.2f}")
    print(f"equity_20251224={equity_20251224:.2f}")


if __name__ == "__main__":
    main()

