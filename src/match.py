
"""Purchase order matching for the invoice automation pipeline.

This module loads approved purchase orders and matches extracted invoice
details against the purchase order database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import pandas as pd

from .schema import Invoice


DEFAULT_PO_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "purchase_orders.csv"
)


@dataclass
class MatchResult:
    """Represents the outcome of matching an invoice to a purchase order."""

    po_found: bool
    po_total: Optional[float]
    po_vendor: Optional[str]
    vendor_known: bool
    po_currency: Optional[str] = None


def normalize(text: str | None) -> str:
    """Normalize text for consistent vendor-name comparison."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def same_vendor(
    a: str | None,
    b: str | None,
    threshold: float = 0.85,
) -> bool:
    """Determine whether two vendor names are sufficiently similar."""
    normalized_a = normalize(a)
    normalized_b = normalize(b)

    if not normalized_a or not normalized_b:
        return False

    similarity = SequenceMatcher(
        None,
        normalized_a,
        normalized_b,
    ).ratio()

    return similarity >= threshold


def load_pos(path: str | Path = DEFAULT_PO_PATH) -> pd.DataFrame:
    """Load purchase orders and prepare normalized PO identifiers."""
    csv_path = Path(path)

    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Purchase order database not found: {csv_path}"
        )

    df = pd.read_csv(csv_path, dtype={"po_number": str})

    required_columns = {
        "po_number",
        "vendor_name",
        "approved_total",
    }
    missing_columns = required_columns.difference(df.columns)

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"Purchase order database is missing required columns: {missing}"
        )

    df["po_key"] = df["po_number"].str.upper().str.strip()

    return df


def match_invoice(
    invoice: Invoice,
    pos: pd.DataFrame,
) -> MatchResult:
    """Match an invoice against the purchase order database.

    Matching uses the purchase order number. Vendor similarity is evaluated
    separately so that a known vendor can still be identified when its PO
    number is missing or does not match.
    """
    vendor_known = any(
        same_vendor(invoice.vendor_name, vendor)
        for vendor in pos["vendor_name"]
    )

    po_key = (invoice.po_number or "").strip().upper()

    if not po_key:
        return MatchResult(
            po_found=False,
            po_total=None,
            po_vendor=None,
            vendor_known=vendor_known,
        )

    matching_rows = pos[pos["po_key"] == po_key]

    if matching_rows.empty:
        return MatchResult(
            po_found=False,
            po_total=None,
            po_vendor=None,
            vendor_known=vendor_known,
        )

    row = matching_rows.iloc[0]

    raw_currency = row.get("currency")

    po_currency = (
        str(raw_currency).strip().upper()
        if pd.notna(raw_currency) and str(raw_currency).strip()
        else None
    )

    return MatchResult(
        po_found=True,
        po_total=float(row["approved_total"]),
        po_vendor=str(row["vendor_name"]),
        vendor_known=vendor_known,
        po_currency=po_currency,
    )
