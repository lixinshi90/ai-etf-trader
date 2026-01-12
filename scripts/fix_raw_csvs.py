# -*- coding: utf-8 -*-
"""
Normalize all CSVs in data/qlib/raw so that qlib dump_bin can process them.
- Ensure there is a 'date' column (rename '日期'/'Date' to 'date')
- Ensure there is a 'symbol' column (fallback to file stem uppercased)
- Parse 'date' as datetime, drop NA & duplicates, sort by date
- Skip files that still don't have 'date' after renaming
- Skip known meta files like instruments.csv if present by mistake
"""
from __future__ import annotations
import os
import glob
import pathlib
import pandas as pd

RAW_DIR = os.path.join("data", "qlib", "raw")

META_FILENAMES = {"instruments.csv", "calendar.csv"}


def main() -> None:
    fixed = 0
    bad: list[str] = []
    if not os.path.isdir(RAW_DIR):
        print("RAW dir not found:", RAW_DIR)
        return

    for fp in glob.glob(os.path.join(RAW_DIR, "*.csv")):
        name = pathlib.Path(fp).name
        if name.lower() in META_FILENAMES:
            print("skip(meta):", fp)
            continue
        stem = pathlib.Path(fp).stem.upper()
        try:
            df = pd.read_csv(fp)
        except Exception as e:
            print("skip(read error):", fp, e)
            continue

        # rename possible date headers
        ren = {}
        for c in df.columns:
            lc = str(c).strip().lower()
            if lc in ("日期", "date", "Date".lower()):
                ren[c] = "date"
        if ren:
            df = df.rename(columns=ren)

        if "date" not in df.columns:
            print("skip(no date):", fp, "cols=", list(df.columns))
            bad.append(fp)
            continue

        # ensure symbol
        if "symbol" not in [str(c).strip().lower() for c in df.columns]:
            df["symbol"] = stem

        # normalize date
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).drop_duplicates(["date"]).sort_values("date")

        try:
            df.to_csv(fp, index=False)
            fixed += 1
            print("fixed:", fp)
        except Exception as e:
            print("skip(write error):", fp, e)

    print("done. fixed:", fixed, "bad:", len(bad))
    if bad:
        print("files still missing 'date':")
        for f in bad:
            print(" -", f)


if __name__ == "__main__":
    main()

