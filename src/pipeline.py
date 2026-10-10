"""Orchestrator: ingest -> extract -> match -> flag -> persist."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from . import history
from .extract import extract_invoice
from .flags import decide_status, risk_score, run_flags
from .ingest import ingest
from .match import load_pos, match_invoice, normalize
from .schema import InvoiceResult


def process(source, filename: Optional[str] = None, pos: Optional[pd.DataFrame] = None,
            db_path=history.DEFAULT_DB) -> InvoiceResult:
    doc = ingest(source, filename)
    invoice = extract_invoice(doc)
    pos = load_pos() if pos is None else pos
    match = match_invoice(invoice, pos)

    vendor_key = normalize(invoice.vendor_name)
    flags = run_flags(
        invoice, match,
        duplicate_file=history.has_hash(db_path, doc.file_hash),
        duplicate_number=history.has_invoice_number(db_path, vendor_key, invoice.invoice_number, doc.file_hash),
    )
    history.save(db_path, doc.file_hash, vendor_key, invoice.invoice_number, doc.filename, invoice.total)

    return InvoiceResult(
        filename=doc.filename, file_hash=doc.file_hash, invoice=invoice,
        po_found=match.po_found, po_total=match.po_total,
        flags=flags, risk_score=risk_score(flags), status=decide_status(flags),
    )
