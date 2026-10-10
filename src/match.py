"""Step 3: Match. Invoice ko Purchase Order (PO) database se compare karna."""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import pandas as pd

from .schema import Invoice

DEFAULT_PO_PATH = Path(__file__).resolve().parent.parent / "data" / "purchase_orders.csv"


@dataclass
class MatchResult:
    po_found: bool
    po_total: Optional[float]
    po_vendor: Optional[str]
    vendor_known: bool


def normalize(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def same_vendor(a: str | None, b: str | None, threshold: float = 0.85) -> bool:
    """Chhote spelling farq (Pvt Ltd vs Pvt. Ltd.) ignore karta hai."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def load_pos(path: str | Path = DEFAULT_PO_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"po_number": str})
    df["po_key"] = df["po_number"].str.upper().str.strip()
    return df


def match_invoice(invoice: Invoice, pos: pd.DataFrame) -> MatchResult:
    vendor_known = any(same_vendor(invoice.vendor_name, v) for v in pos["vendor_name"])

    po_key = (invoice.po_number or "").upper().strip()
    row = pos[pos["po_key"] == po_key] if po_key else pos.iloc[0:0]
    if row.empty:
        return MatchResult(False, None, None, vendor_known)

    row = row.iloc[0]
    return MatchResult(True, float(row["approved_total"]), str(row["vendor_name"]), vendor_known)
