
"""Step 4: Flag. Rules that catch suspicious invoices.

Each rule returns a list[Flag] (code, severity, message).
Missing or invalid totals must not be silently approved.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Optional

from . import fx
from .match import MatchResult, same_vendor
from .schema import Flag, Invoice

WEIGHTS = {"low": 10, "medium": 20, "high": 40}

MISMATCH_MEDIUM_PCT = 0.02
MISMATCH_HIGH_PCT = 0.10
FX_SLACK_PCT = 0.03
MATH_TOLERANCE = 1.0


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None

    for fmt in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue

    return None


class Ctx:
    """Everything a rule needs, gathered in one place."""

    def __init__(
        self,
        invoice: Invoice,
        match: MatchResult,
        duplicate_file: bool,
        duplicate_number: bool,
        today: date,
    ):
        self.invoice = invoice
        self.match = match
        self.duplicate_file = duplicate_file
        self.duplicate_number = duplicate_number
        self.today = today


def rule_duplicate_file(c: Ctx) -> list[Flag]:
    if c.duplicate_file:
        return [
            Flag(
                code="DUPLICATE_FILE",
                severity="high",
                message="This exact file has already been processed.",
            )
        ]
    return []


def rule_duplicate_number(c: Ctx) -> list[Flag]:
    if c.duplicate_number:
        return [
            Flag(
                code="DUPLICATE_INVOICE_NUMBER",
                severity="high",
                message=(
                    f"Invoice number {c.invoice.invoice_number} "
                    "was already submitted by this vendor in a different file."
                ),
            )
        ]
    return []


def rule_po(c: Ctx) -> list[Flag]:
    inv, match = c.invoice, c.match

    if not inv.po_number:
        return [
            Flag(
                code="NO_PO_NUMBER",
                severity="medium",
                message="No PO number appears on the invoice.",
            )
        ]

    if not match.po_found:
        return [
            Flag(
                code="PO_NOT_FOUND",
                severity="high",
                message=(
                    f"PO {inv.po_number} was not found "
                    "in the purchase-order database."
                ),
            )
        ]

    return []


def rule_vendor(c: Ctx) -> list[Flag]:
    inv, match = c.invoice, c.match
    flags: list[Flag] = []

    if not match.vendor_known:
        flags.append(
            Flag(
                code="UNKNOWN_VENDOR",
                severity="medium",
                message=(
                    f"Vendor '{inv.vendor_name}' is not on "
                    "the approved vendor list."
                ),
            )
        )

    if match.po_found and not same_vendor(inv.vendor_name, match.po_vendor):
        flags.append(
            Flag(
                code="VENDOR_MISMATCH",
                severity="high",
                message=(
                    f"Invoice vendor '{inv.vendor_name}' differs "
                    f"from the PO vendor '{match.po_vendor}'."
                ),
            )
        )

    return flags


def rule_total(c: Ctx) -> list[Flag]:
    """Flag a missing, zero, negative, or non-finite invoice total."""
    total = c.invoice.total

    if total is None or not isinstance(total, (int, float)):
        invalid = True
    else:
        import math
        invalid = not math.isfinite(total) or total <= 0

    if invalid:
        return [
            Flag(
                code="TOTAL_MISSING_OR_INVALID",
                severity="medium",
                tier="critical",
                message=(
                    "Invoice total is zero, missing, or invalid. "
                    "Verify the amount against the original invoice."
                ),
            )
        ]

    return []


def rule_amount(c: Ctx) -> list[Flag]:
    inv, match = c.invoice, c.match

    if not match.po_found:
        return []

    if match.po_total is None or match.po_total <= 0:
        return []

    flags: list[Flag] = []
    po_cur = (match.po_currency or inv.currency or "INR").upper()
    inv_cur = (inv.currency or po_cur).upper()
    total, slack = inv.total, 0.0

    if inv_cur != po_cur:
        converted = fx.convert(inv.total, inv_cur, po_cur)

        if converted is None:
            return [
                Flag(
                    code="UNSUPPORTED_CURRENCY",
                    severity="medium",
                    message=(
                        f"Cannot verify {inv_cur} against a {po_cur} "
                        "purchase order: no exchange rate on file."
                    ),
                )
            ]

        flags.append(
            Flag(
                code="CURRENCY_MISMATCH",
                severity="medium",
                message=(
                    f"Invoice is in {inv_cur} but the PO was raised "
                    f"in {po_cur}; compared at indicative rates."
                ),
            )
        )
        total, slack = converted, FX_SLACK_PCT

    diff = total - match.po_total
    pct = abs(diff) / match.po_total

    if pct <= MISMATCH_MEDIUM_PCT + slack:
        return flags

    severity = (
        "high"
        if pct > MISMATCH_HIGH_PCT + slack
        else "medium"
    )

    flags.append(
        Flag(
            code="AMOUNT_MISMATCH",
            severity=severity,
            message=(
                f"Invoice total {inv.total:,.2f} {inv_cur} versus "
                f"approved PO total {match.po_total:,.2f} {po_cur} "
                f"(variance {diff:+,.2f} {po_cur}, {pct:.1%})."
            ),
        )
    )

    return flags


def rule_math(c: Ctx) -> list[Flag]:
    inv = c.invoice
    flags: list[Flag] = []

    if inv.line_items and inv.subtotal is not None:
        items_sum = sum(item.amount for item in inv.line_items)

        if abs(items_sum - inv.subtotal) > MATH_TOLERANCE:
            flags.append(
                Flag(
                    code="LINE_ITEMS_MISMATCH",
                    severity="medium",
                    tier="supporting",
                    message=(
                        f"Line items sum to {items_sum:,.2f}, "
                        f"but the stated subtotal is {inv.subtotal:,.2f}."
                    ),
                )
            )

    if inv.subtotal is not None and inv.tax is not None:
        if abs(inv.subtotal + inv.tax - inv.total) > MATH_TOLERANCE:
            flags.append(
                Flag(
                    code="TOTAL_MATH_ERROR",
                    severity="medium",
                    tier="supporting",
                    message="Subtotal plus tax does not equal the stated total.",
                )
            )

    return flags


def rule_date(c: Ctx) -> list[Flag]:
    parsed_date = _parse_date(c.invoice.invoice_date)

    if c.invoice.invoice_date and parsed_date is None:
        return [
            Flag(
                code="BAD_DATE",
                severity="low",
                tier="supporting",
                message="The invoice date could not be parsed.",
            )
        ]

    if parsed_date and parsed_date > c.today:
        return [
            Flag(
                code="FUTURE_DATE",
                severity="medium",
                tier="supporting",
                message=f"Invoice date {parsed_date} lies in the future.",
            )
        ]

    return []


RULES: list[Callable[[Ctx], list[Flag]]] = [
    rule_duplicate_file,
    rule_duplicate_number,
    rule_po,
    rule_vendor,
    rule_total,
    rule_amount,
    rule_math,
    rule_date,
]


def run_flags(
    invoice: Invoice,
    match: MatchResult,
    *,
    duplicate_file: bool = False,
    duplicate_number: bool = False,
    today: Optional[date] = None,
) -> list[Flag]:
    ctx = Ctx(
        invoice,
        match,
        duplicate_file,
        duplicate_number,
        today or date.today(),
    )

    flags: list[Flag] = []
    for rule in RULES:
        flags.extend(rule(ctx))

    return flags


def risk_score(flags: list[Flag]) -> int:
    return min(100, sum(WEIGHTS[flag.severity] for flag in flags))


def decide_status(flags: list[Flag]) -> str:
    """Reject serious critical issues and review uncertain invoices."""
    if any(
        flag.tier == "critical" and flag.severity == "high"
        for flag in flags
    ):
        return "reject"

    if any(flag.tier == "critical" for flag in flags):
        return "review"

    if any(flag.severity != "low" for flag in flags):
        return "review"

    return "approve"
