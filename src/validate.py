"""Step 2b: the evidence-grounded validation gate.

Extraction is probabilistic; money is not. Before any extracted value is allowed
to influence a verdict, the gate demands evidence for it in the source document
and separates hard prerequisites from negotiable details:

  * Critical fields (invoice number, vendor, PO, total) must be traceable to the
    document text. An ungrounded critical value is a high-severity finding.
  * Supporting fields (subtotal, tax, date) are checked too, but a failure is
    only advisory and can never reject an invoice.
  * Noisy boilerplate (late fees, discount terms, references to other invoices)
    is recognised and ignored instead of being mistaken for the invoice total.
  * A genuinely contradictory total ("Total" vs "Revised total") is surfaced as
    one explicit finding rather than silently picking a number.

Amounts and dates are compared numerically after locale-aware parsing, so
"2.975,00", "2,975.00" and "1,18,000.00" are all understood as what they mean.
"""
from __future__ import annotations

import re

from .ingest import IngestedDoc
from .labels import AMOUNT_NAMED, TAIL, TOTAL
from .locale_utils import dates_in_text, parse_amount
from .schema import Flag, GateReport, Invoice

_TOTAL_LINE = re.compile(
    r"^\s*(?P<label>(?:revised\s+)?" + TOTAL + r")\s*[:\-]?\s*" + AMOUNT_NAMED + TAIL, re.I)
_MONEY_WORDS = re.compile(
    r"fee|discount|charge|total|payable|payment|penalt|interest|gebühr|rabatt|skonto|zahlbetrag|frais|remise|escompte|descuento|recargo", re.I)
_STRUCTURAL = re.compile(r"^\s*(?:sub\s*-?total|zwischensumme|sous-?total|imponibile|tax|gst|vat|mwst|ust|tva|iva)\b", re.I)
_NUM_TOKEN = re.compile(r"\d[\d.,'\u00a0\u202f]*\d|\d")


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _numbers_in(text: str) -> set[float]:
    values = (parse_amount(token) for token in _NUM_TOKEN.findall(text))
    return {round(v, 2) for v in values if v is not None}


def run_gate(doc: IngestedDoc, invoice: Invoice) -> tuple[GateReport, list[Flag]]:
    report, flags = GateReport(), []

    if doc.kind != "text":
        report.grounded = False
        report.notes.append("Image input: text evidence is unavailable, grounding skipped.")
        return report, flags

    text, squashed, numbers = doc.text, _squash(doc.text), _numbers_in(doc.text)

    def record(field: str, present: bool) -> None:
        (report.verified if present else report.unverified).append(field)

    # Critical fields: present and traceable, or a high-severity finding.
    for field, value in (("invoice_number", invoice.invoice_number), ("vendor_name", invoice.vendor_name)):
        label = field.replace("_", " ")
        if not value:
            flags.append(Flag(code="MISSING_FIELD", severity="high", message=f"No {label} could be extracted."))
            continue
        ok = _squash(value) in squashed
        record(field, ok)
        if not ok:
            flags.append(Flag(code="EVIDENCE_MISSING", severity="high",
                              message=f"Extracted {label} '{value}' cannot be traced to the document text."))

    if invoice.po_number:
        ok = _squash(invoice.po_number) in squashed
        record("po_number", ok)
        if not ok:
            flags.append(Flag(code="EVIDENCE_MISSING", severity="high",
                              message=f"Extracted PO number '{invoice.po_number}' cannot be traced to the document text."))

    if not invoice.total:
        flags.append(Flag(code="MISSING_FIELD", severity="high", message="No invoice total could be extracted."))
    else:
        ok = round(invoice.total, 2) in numbers
        record("total", ok)
        if not ok:
            flags.append(Flag(code="EVIDENCE_MISSING", severity="high",
                              message=f"Extracted total {invoice.total:,.2f} cannot be traced to the document text."))

    # Supporting fields: advisory only.
    for field, value in (("subtotal", invoice.subtotal), ("tax", invoice.tax)):
        if value is not None:
            ok = round(value, 2) in numbers
            record(field, ok)
            if not ok:
                flags.append(Flag(code="EVIDENCE_MISSING", severity="low", tier="supporting",
                                  message=f"Extracted {field} {value:,.2f} cannot be traced to the document text."))
    if invoice.invoice_date:
        ok = invoice.invoice_date in dates_in_text(text) or invoice.invoice_date in text
        record("invoice_date", ok)
        if not ok:
            flags.append(Flag(code="EVIDENCE_MISSING", severity="low", tier="supporting",
                              message=f"Extracted date {invoice.invoice_date} cannot be traced to the document text."))

    # Contradictory totals: every labelled total must agree with the extracted one.
    candidates = []
    for line in text.splitlines():
        match = _TOTAL_LINE.match(line)
        amount = parse_amount(match["amt"]) if match else None
        if match and amount is not None:
            candidates.append((match["label"].strip().title(), amount, line.strip()))
    for label, amount, _ in candidates:
        if invoice.total and abs(amount - invoice.total) > 0.005:
            flags.append(Flag(code="CONFLICTING_TOTALS", severity="high",
                              message=f"The document also states '{label}: {amount:,.2f}', "
                                      f"which conflicts with the extracted total {invoice.total:,.2f}."))
    if invoice.subtotal is not None and invoice.tax is not None and invoice.total \
            and abs(invoice.subtotal + invoice.tax - invoice.total) <= 1:
        report.notes.append("Extracted total reconciles with subtotal plus tax.")

    # Boilerplate that mentions money but is not part of the invoice arithmetic.
    labelled = {line for *_, line in candidates}
    for raw in text.splitlines():
        line = raw.strip()
        if line and line not in labelled and re.search(r"\d", line) \
                and _MONEY_WORDS.search(line) and not _STRUCTURAL.match(line):
            report.ignored_noise.append(line)

    return report, flags