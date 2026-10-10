from datetime import date

import pytest

from scripts.make_samples import build
from src.flags import decide_status, run_flags
from src.match import MatchResult
from src.pipeline import process
from src.schema import Invoice, LineItem


@pytest.fixture()
def corpus(tmp_path):
    return {p.name: p for p in build(tmp_path / "samples")}


def codes(result):
    return {f.code for f in result.flags}


def test_end_to_end_flags(corpus, tmp_path):
    db = tmp_path / "history.db"
    run = lambda name: process(corpus[name], db_path=db)

    clean = run("01_clean.pdf")
    assert clean.status == "approve" and clean.invoice.total == 59000

    assert "AMOUNT_MISMATCH" in codes(run("02_amount_mismatch.pdf"))
    assert "DUPLICATE_FILE" in codes(run("03_exact_duplicate.pdf"))

    unknown = run("04_unknown_vendor.pdf")
    assert {"UNKNOWN_VENDOR", "PO_NOT_FOUND", "LINE_ITEMS_MISMATCH"} <= codes(unknown)
    assert unknown.status == "reject"

    assert "DUPLICATE_INVOICE_NUMBER" in codes(run("05_resubmitted_number.pdf"))


def test_future_date_and_math_rules():
    invoice = Invoice(invoice_number="X1", vendor_name="ABC Traders Pvt Ltd", po_number="PO-1001",
                      invoice_date="2030-01-01", subtotal=100, tax=18, total=130,
                      line_items=[LineItem(amount=100)])
    match = MatchResult(True, 130.0, "ABC Traders Pvt Ltd", True)
    flags = run_flags(invoice, match, today=date(2026, 10, 11))
    assert {f.code for f in flags} == {"FUTURE_DATE", "TOTAL_MATH_ERROR"}
    assert decide_status(flags) == "review"
