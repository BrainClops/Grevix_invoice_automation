"""Orchestrator: ingest -> extract -> gate -> match -> flag -> persist."""
from __future__ import annotations

import time
from typing import Optional

import pandas as pd

from . import history
from .extract import extract_invoice
from .flags import WEIGHTS, decide_status, risk_score, run_flags
from .ingest import ingest
from .match import load_pos, match_invoice, normalize
from .schema import InvoiceResult
from .validate import run_gate


def _timed(timings: dict, key: str, fn, *args, **kwargs):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    timings[key] = round((time.perf_counter() - start) * 1000, 2)
    return result


def process(source, filename: Optional[str] = None, pos: Optional[pd.DataFrame] = None,
            db_path=history.DEFAULT_DB, gate: bool = True) -> InvoiceResult:
    timings: dict[str, float] = {}
    doc = _timed(timings, "ingest", ingest, source, filename)
    invoice = _timed(timings, "extract", extract_invoice, doc)
    pos = load_pos() if pos is None else pos

    report, gate_flags = (None, [])
    if gate:
        report, gate_flags = _timed(timings, "gate", run_gate, doc, invoice)

    match = _timed(timings, "match", match_invoice, invoice, pos)
    vendor_key = normalize(invoice.vendor_name)
    rule_flags = _timed(
        timings, "flags", run_flags, invoice, match,
        duplicate_file=history.has_hash(db_path, doc.file_hash),
        duplicate_number=history.has_invoice_number(db_path, vendor_key, invoice.invoice_number, doc.file_hash),
    )
    flags = gate_flags + rule_flags

    if report is not None:
        serious = sorted((f for f in flags if f.tier == "critical" and f.severity in ("high", "medium")),
                         key=lambda f: WEIGHTS[f.severity], reverse=True)
        report.genuine_issues = list(dict.fromkeys(f.code for f in serious))[:3]

    history.save(db_path, doc.file_hash, vendor_key, invoice.invoice_number, doc.filename, invoice.total)
    return InvoiceResult(
        filename=doc.filename, file_hash=doc.file_hash, invoice=invoice,
        po_found=match.po_found, po_total=match.po_total, po_currency=match.po_currency,
        flags=flags, risk_score=risk_score(flags), status=decide_status(flags),
        gate=report, timings_ms=timings,
    )
