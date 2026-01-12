from __future__ import annotations

import csv
import re
from pathlib import Path

LOG_PATH = Path("logs/daily.log")
OUT_PATH = Path("out/holdings_breakdown_2025-12-24.csv")

# Parse the *last* equity-breakdown block for 2025-12-24.
LINE_RE = re.compile(
    r"^2025-12-24\s+\d{2}:\d{2}:\d{2},\d{3}\s+INFO\s+\[equity-breakdown\]\s+"
    r"(?P<code>\d{6})\s+qty=(?P<qty>[-0-9.]+)\s+px=(?P<px>[-0-9.]+)\s+val=(?P<val>[-0-9.]+)"
)


def main() -> None:
    if not LOG_PATH.exists():
        raise FileNotFoundError(LOG_PATH)

    rows: dict[str, tuple[float, float]] = {}
    last_seen_any = False

    with LOG_PATH.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = LINE_RE.match(line.strip())
            if not m:
                continue
            last_seen_any = True
            code = m.group("code")
            qty = float(m.group("qty"))
            px = float(m.group("px"))
            rows[code] = (qty, px)

    if not last_seen_any:
        raise RuntimeError("No 2025-12-24 equity-breakdown lines found in daily.log")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "qty_asof", "close_asof", "value", "flags"])
        for code in sorted(rows.keys()):
            qty, px = rows[code]
            w.writerow([code, qty, px, qty * px, ""])

    print(f"[ok] wrote: {OUT_PATH}")
    print(f"[info] codes={len(rows)}")


if __name__ == "__main__":
    main()

