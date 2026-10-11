"""Indicative currency conversion from a static table (data/fx_rates.csv).

The rates are illustrative so the system works offline; a production deployment
would replace `_load` with a live feed and keep the same `convert` contract.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

FX_PATH = Path(__file__).resolve().parent.parent / "data" / "fx_rates.csv"
_rates: Optional[dict[str, float]] = None


def _load() -> dict[str, float]:
    global _rates
    if _rates is None:
        with open(FX_PATH, newline="", encoding="utf-8") as handle:
            _rates = {row["currency"].upper(): float(row["units_per_usd"]) for row in csv.DictReader(handle)}
    return _rates


def convert(amount: float, src: str, dst: str) -> Optional[float]:
    src, dst = src.upper(), dst.upper()
    if src == dst:
        return amount
    rates = _load()
    if src not in rates or dst not in rates:
        return None
    return amount / rates[src] * rates[dst]
