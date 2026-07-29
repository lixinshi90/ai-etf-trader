from __future__ import annotations

from pathlib import Path
import re

SRC_LOG = Path("logs/daily.log")
DST_LOG = Path("logs/daily.corrected.log")

# User-approved invariant for 2025-12-23
EQUITY_20251223 = 99795.48
HOLDINGS_20251223 = 57449.23
CASH_20251223_CORRECTED = round(EQUITY_20251223 - HOLDINGS_20251223, 2)  # 42346.25

# 2025-12-24 holdings (no-trade; revalued by 12/24 close) from daily.log
HOLDINGS_20251224 = 57578.72
EQUITY_20251224_CORRECTED = round(CASH_20251223_CORRECTED + HOLDINGS_20251224, 2)  # 99924.97

# Match the daily equity-breakdown summary line:
# 2025-12-23 ... INFO [equity-breakdown] cash=52476.44 holdings=57449.23 missing_px=[]
SUMMARY_RE = re.compile(
    r"^(?P<prefix>2025\-12\-(?P<day>23|24)\s+\d{2}:\d{2}:\d{2},\d{3}\s+INFO\s+\[equity-breakdown\]\s+)"
    r"cash=(?P<cash>[-0-9.]+)\s+holdings=(?P<holdings>[-0-9.]+)(?P<suffix>\s+missing_px=\[.*\]\s*)$"
)

# Match the snapshot write line:
# 2025-12-23 ... INFO 已写入日终快照 2025-12-23: 99795.48
SNAPSHOT_RE = re.compile(
    r"^(?P<prefix>2025\-12\-(?P<day>23|24)\s+\d{2}:\d{2}:\d{2},\d{3}\s+INFO\s+已写入日终快照\s+)"
    r"(?P<date>2025\-12\-(?P=day)):\s+(?P<equity>[-0-9.]+)\s*$"
)

# Match the guard rejection line (we will keep it but also add a corrected snapshot line)
GUARD_REJECT_RE = re.compile(
    r"^(?P<prefix>2025\-12\-24\s+\d{2}:\d{2}:\d{2},\d{3}\s+ERROR\s+\[equity-guard\]\s+拒绝写入日终快照\s+2025\-12\-24:\s+)"
    r"(?P<equity>[-0-9.]+)(?P<suffix>\s+\|\s+reason=.*)$"
)


def main() -> None:
    if not SRC_LOG.exists():
        raise FileNotFoundError(f"Source log not found: {SRC_LOG}")

    out_lines: list[str] = []
    injected_20251224_snapshot = False

    with SRC_LOG.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = SUMMARY_RE.match(line.rstrip("\n"))
            if m:
                day = m.group("day")
                if day == "23":
                    new_line = (
                        f"{m.group('prefix')}cash={CASH_20251223_CORRECTED:.2f} "
                        f"holdings={HOLDINGS_20251223:.2f}{m.group('suffix')}\n"
                    )
                    out_lines.append(new_line)
                    continue
                if day == "24":
                    new_line = (
                        f"{m.group('prefix')}cash={CASH_20251223_CORRECTED:.2f} "
                        f"holdings={HOLDINGS_20251224:.2f}{m.group('suffix')}\n"
                    )
                    out_lines.append(new_line)
                    continue

            m = SNAPSHOT_RE.match(line.rstrip("\n"))
            if m:
                day = m.group("day")
                if day == "23":
                    # Keep as-is (already matches approved equity)
                    out_lines.append(line)
                    continue
                if day == "24":
                    # If there is an existing 12/24 snapshot line, overwrite it to corrected value
                    new_line = f"{m.group('prefix')}{m.group('date')}: {EQUITY_20251224_CORRECTED:.2f}\n"
                    out_lines.append(new_line)
                    injected_20251224_snapshot = True
                    continue

            m = GUARD_REJECT_RE.match(line.rstrip("\n"))
            if m:
                # Keep the rejection line for auditability
                out_lines.append(line)

                # Inject an explicit corrected snapshot line right after it (if not already present later)
                if not injected_20251224_snapshot:
                    # Reuse same timestamp/prefix style but as INFO
                    # Transform ERROR prefix to INFO and message to indicate corrected equity.
                    # Example:
                    # 2025-12-24 ... INFO [equity-corrected] 应写入日终快照 2025-12-24: 99924.97 | reason=no-trade revaluation with corrected cash
                    info_prefix = m.group('prefix').replace("ERROR", "INFO").replace("[equity-guard]", "[equity-corrected]")
                    injected = (
                        f"{info_prefix}{EQUITY_20251224_CORRECTED:.2f} | "
                        f"reason=2025-12-23 equity fixed at {EQUITY_20251223:.2f}, holdings_20251224={HOLDINGS_20251224:.2f}, cash corrected to {CASH_20251223_CORRECTED:.2f}\n"
                    )
                    out_lines.append(injected)
                    injected_20251224_snapshot = True
                continue

            out_lines.append(line)

    DST_LOG.parent.mkdir(parents=True, exist_ok=True)
    DST_LOG.write_text("".join(out_lines), encoding="utf-8")

    print(f"[ok] wrote: {DST_LOG}")
    print(f"[summary] cash_2025-12-23 corrected to {CASH_20251223_CORRECTED:.2f}")
    print(f"[summary] equity_2025-12-24 corrected to {EQUITY_20251224_CORRECTED:.2f}")


if __name__ == "__main__":
    main()

