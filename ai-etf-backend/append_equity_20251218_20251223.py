import pandas as pd
from pathlib import Path

CSV_PATH = Path("out/corrected_daily_equity.csv")

ADD = {
    "2025-12-18": 99499.70,
    "2025-12-19": 99844.89,
    "2025-12-22": 99906.27,
    "2025-12-23": 99795.48,
}


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)
    if "date" not in df.columns or "equity" not in df.columns:
        raise ValueError("CSV must have columns: date,equity")

    # Normalize date format so de-dup works reliably
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    add_df = pd.DataFrame([{"date": d, "equity": float(v)} for d, v in ADD.items()])
    out = pd.concat([df, add_df], ignore_index=True)

    # Keep only one row per date; last wins so ADD overrides existing values
    out = out.drop_duplicates(subset=["date"], keep="last")

    # Sort by date ascending
    out["_date_sort"] = pd.to_datetime(out["date"])
    out = out.sort_values("_date_sort").drop(columns=["_date_sort"])

    out.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    print(f"[ok] wrote: {CSV_PATH}")
    print(out.tail(15).to_string(index=False))


if __name__ == "__main__":
    main()

