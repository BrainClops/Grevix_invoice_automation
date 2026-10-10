"""Step 4: Flag. Rules that catch suspicious invoices.

Each rule returns a list[Flag] (code, severity, message). To add a new control,
write one function and append it to RULES.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Optional

from .match import MatchResult, same_vendor
from .schema import Flag, Invoice

WEIGHTS = {"low": 10, "medium": 20, "high": 40}

MISMATCH_MEDIUM_PCT = 0.02  # above 2% = medium
MISMATCH_HIGH_PCT = 0.10    # above 10% = high
MATH_TOLERANCE = 1.0        # tolerate tiny rounding differences


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


class Ctx:
    """Everything a rule needs, gathered in one place."""

    def __init__(self, invoice: Invoice, match: MatchResult,
                 duplicate_file: bool, duplicate_number: bool, today: date):
        self.invoice = invoice
        self.match = match
        self.duplicate_file = duplicate_file
        self.duplicate_number = duplicate_number
        self.today = today


def rule_duplicate_file(c: Ctx) -> list[Flag]:
    if c.duplicate_file:
        return [Flag(code="DUPLICATE_FILE", severity="high",
                     message="This exact file has already been processed.")]
    return []


def rule_duplicate_number(c: Ctx) -> list[Flag]:
    if c.duplicate_number:
        return [Flag(code="DUPLICATE_INVOICE_NUMBER", severity="high",
                     message=f"Invoice number {c.invoice.invoice_number} was already submitted by this vendor in a different file.")]
    return []


def rule_po(c: Ctx) -> list[Flag]:
    inv, m = c.invoice, c.match
    if not inv.po_number:
        return [Flag(code="NO_PO_NUMBER", severity="medium",
                     message="No PO number appears on the invoice.")]
    if not m.po_found:
        return [Flag(code="PO_NOT_FOUND", severity="high",
                     message=f"PO {inv.po_number} was not found in the purchase-order database.")]
    return []


def rule_vendor(c: Ctx) -> list[Flag]:
    inv, m = c.invoice, c.match
    flags: list[Flag] = []
    if not m.vendor_known:
        flags.append(Flag(code="UNKNOWN_VENDOR", severity="medium",
                          message=f"Vendor '{inv.vendor_name}' is not on the approved vendor list."))
    if m.po_found and not same_vendor(inv.vendor_name, m.po_vendor):
        flags.append(Flag(code="VENDOR_MISMATCH", severity="high",
                          message=f"Invoice vendor '{inv.vendor_name}' differs from the PO vendor '{m.po_vendor}'."))
    return flags


def rule_amount(c: Ctx) -> list[Flag]:
    inv, m = c.invoice, c.match
    if not m.po_found or not m.po_total:
        return []
    diff = inv.total - m.po_total
    pct = abs(diff) / m.po_total
    if pct <= MISMATCH_MEDIUM_PCT:
        return []
    severity = "high" if pct > MISMATCH_HIGH_PCT else "medium"
    return [Flag(code="AMOUNT_MISMATCH", severity=severity,
                 message=f"Invoice total {inv.total:,.2f} versus approved PO total {m.po_total:,.2f} "
                         f"(variance {diff:+,.2f}, {pct:.1%}).")]


def rule_math(c: Ctx) -> list[Flag]:
    inv = c.invoice
    flags: list[Flag] = []
    if inv.line_items and inv.subtotal is not None:
        items_sum = sum(i.amount for i in inv.line_items)
        if abs(items_sum - inv.subtotal) > MATH_TOLERANCE:
            flags.append(Flag(code="LINE_ITEMS_MISMATCH", severity="medium",
                              message=f"Line items sum to {items_sum:,.2f}, but the stated subtotal is {inv.subtotal:,.2f}."))
    if inv.subtotal is not None and inv.tax is not None:
        if abs(inv.subtotal + inv.tax - inv.total) > MATH_TOLERANCE:
            flags.append(Flag(code="TOTAL_MATH_ERROR", severity="medium",
                              message="Subtotal plus tax does not equal the stated total."))
    return flags


def rule_date(c: Ctx) -> list[Flag]:
    d = _parse_date(c.invoice.invoice_date)
    if c.invoice.invoice_date and d is None:
        return [Flag(code="BAD_DATE", severity="low", message="The invoice date could not be parsed.")]
    if d and d > c.today:
        return [Flag(code="FUTURE_DATE", severity="medium",
                     message=f"Invoice date {d} lies in the future.")]
    return []


RULES: list[Callable[[Ctx], list[Flag]]] = [
    rule_duplicate_file, rule_duplicate_number, rule_po,
    rule_vendor, rule_amount, rule_math, rule_date,
]


def run_flags(invoice: Invoice, match: MatchResult, *, duplicate_file: bool = False,
              duplicate_number: bool = False, today: Optional[date] = None) -> list[Flag]:
    ctx = Ctx(invoice, match, duplicate_file, duplicate_number, today or date.today())
    flags: list[Flag] = []
    for rule in RULES:
        flags.extend(rule(ctx))
    return flags


def risk_score(flags: list[Flag]) -> int:
    return min(100, sum(WEIGHTS[f.severity] for f in flags))


def decide_status(flags: list[Flag]) -> str:
    if any(f.severity == "high" for f in flags):
        return "reject"
    if flags:
        return "review"
    return "approve"