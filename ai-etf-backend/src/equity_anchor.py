from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EquityAnchorResult:
    cash: float
    positions: Dict[str, Dict[str, float]]  # code -> position dict (expects key "quantity")
    note: str


def _read_corrected_equity_rows(csv_path: Path) -> list[tuple[str, float]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"corrected equity csv not found: {csv_path}")

    rows: list[tuple[str, float]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "date" not in reader.fieldnames or "equity" not in reader.fieldnames:
            raise ValueError(f"{csv_path} must have columns: date,equity")
        for r in reader:
            d = (r.get("date") or "").strip()
            if not d:
                continue
            rows.append((d, float(r["equity"])))

    # Assume csv already sorted ascending by date (we also keep stable order)
    return rows


def _prev_trading_day_from_csv(rows: list[tuple[str, float]], date_str: str) -> tuple[str, float]:
    # Find the last row strictly < date_str (lexicographic works for YYYY-MM-DD)
    prev = None
    for d, eq in rows:
        if d < date_str:
            prev = (d, eq)
        else:
            break
    if not prev:
        raise ValueError(f"No previous trading day found in corrected equity csv for date={date_str}")
    return prev


def _load_holdings_breakdown_value_and_qty(
    breakdown_path: Path,
) -> tuple[float, Dict[str, float]]:
    """Return (holdings_value, qty_by_code) using qty_asof/close_asof when present.

    NOTE: value column is ignored; we recompute from qty*close to avoid inconsistencies.
    """
    if not breakdown_path.exists():
        raise FileNotFoundError(f"holdings breakdown not found: {breakdown_path}")

    hv = 0.0
    qty_by_code: Dict[str, float] = {}

    with breakdown_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"empty holdings breakdown csv: {breakdown_path}")

        for r in reader:
            code = str(r.get("code") or "").strip()
            if not code:
                continue
            qty = r.get("qty_asof") if r.get("qty_asof") is not None else r.get("qty")
            close = r.get("close_asof") if r.get("close_asof") is not None else r.get("close")
            if qty is None or close is None:
                raise ValueError(f"{breakdown_path} must have qty_asof/close_asof (or qty/close) for code={code}")
            q = float(qty)
            c = float(close)
            hv += q * c
            qty_by_code[code] = q

    return hv, qty_by_code


def anchor_account_to_corrected_equity(
    *,
    date_str: str,
    recovered_cash: float,
    positions: Dict[str, Dict[str, float]],
    corrected_equity_csv: str | Path = "out/corrected_daily_equity.csv",
    holdings_breakdown_dir: str | Path = "out",
    allow_scale_positions_if_negative_cash: bool = True,
) -> EquityAnchorResult:
    """Force the recovered account state to be consistent with corrected equity.

    Strategy:
    - Use the previous *trading day* from corrected_daily_equity.csv as anchor (not calendar -1 day).
    - Compute holdings value from out/holdings_breakdown_<prev>.csv.
    - Set cash = equity_prev - holdings_prev.

    If cash becomes negative:
    - If allow_scale_positions_if_negative_cash, scale all positions down proportionally to make cash=0.
    - Else raise.

    This prevents "cash created from nowhere" during recovery, enforcing no-leverage/no-overspend.
    """

    corrected_path = Path(corrected_equity_csv)
    rows = _read_corrected_equity_rows(corrected_path)
    prev_day, target_equity = _prev_trading_day_from_csv(rows, date_str)

    breakdown_path = Path(holdings_breakdown_dir) / f"holdings_breakdown_{prev_day}.csv"
    holdings_value, qty_by_code = _load_holdings_breakdown_value_and_qty(breakdown_path)

    cash = round(target_equity - holdings_value, 2)
    note = (
        f"anchor prev={prev_day} equity={target_equity:.2f} holdings={holdings_value:.2f} "
        f"| cash {recovered_cash:.2f}->{cash:.2f}"
    )

    if cash >= 0:
        return EquityAnchorResult(cash=cash, positions=positions, note=note)

    if not allow_scale_positions_if_negative_cash:
        raise ValueError(note + " | cash<0")

    # Scale down positions (quantities) so holdings_value becomes exactly target_equity.
    # This enforces no leverage by making cash=0.
    if holdings_value <= 0:
        return EquityAnchorResult(cash=0.0, positions={}, note=note + " | holdings<=0, cleared")

    scale = max(0.0, target_equity / holdings_value)

    new_positions: Dict[str, Dict[str, float]] = {}
    for code, pos in positions.items():
        q = float(pos.get("quantity", 0) or 0)
        if q <= 0:
            continue
        new_positions[code] = {**pos, "quantity": q * scale}

    cash2 = 0.0
    note2 = note + f" | cash<0, scaled positions by {scale:.6f}, set cash=0"
    logger.warning(note2)
    return EquityAnchorResult(cash=cash2, positions=new_positions, note=note2)

