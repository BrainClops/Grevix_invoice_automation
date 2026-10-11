import pytest

from scripts.make_samples import build
from src import fx
from src.flags import run_flags
from src.locale_utils import detect_currency, normalize_date, parse_amount
from src.match import load_pos, match_invoice
from src.pipeline import process
from src.schema import Invoice


@pytest.fixture()
def corpus(tmp_path):
    return {p.name: p for p in build(tmp_path / "samples")}


@pytest.mark.parametrize("raw,expected", [
    ("118,000.00", 118000.0), ("1,18,000.00", 118000.0), ("118.000,00", 118000.0), ("118'000.00", 118000.0),
    ("2.975,00", 2975.0), ("475,00", 475.0), ("1,180", 1180.0), ("Rs. 5,000", 5000.0), ("$12,420.00", 12420.0),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("08.10.2026", "2026-10-08"), ("09/25/2026", "2026-09-25"), ("25/09/2026", "2026-09-25"), ("2026-10-08", "2026-10-08"),
])
def test_normalize_date(raw, expected):
    assert normalize_date(raw) == expected


def test_detect_currency():
    assert detect_currency("Total: €120") == "EUR"
    assert detect_currency("Währung: GBP") == "GBP"


def test_global_samples_are_understood(corpus, tmp_path):
    db = tmp_path / "h.db"
    german = process(corpus["07_german_eur.pdf"], db_path=db)
    assert (german.invoice.currency, german.invoice.total, german.invoice.invoice_date) == ("EUR", 2975.0, "2026-10-08")
    assert german.invoice.vendor_name == "Müller Elektronik GmbH"
    assert german.status == "approve" and len(german.gate.ignored_noise) == 1

    american = process(corpus["08_us_usd.pdf"], db_path=db)
    assert (american.invoice.currency, american.invoice.total, american.invoice.invoice_date) == ("USD", 12420.0, "2026-09-25")
    assert american.status == "approve"


def test_currency_mismatch_is_converted_not_blindly_rejected():
    pos = load_pos()
    invoice = Invoice(vendor_name="Müller Elektronik GmbH", po_number="PO-2001", currency="USD",
                      total=fx.convert(2975.0, "EUR", "USD"))
    codes = {f.code for f in run_flags(invoice, match_invoice(invoice, pos))}
    assert "CURRENCY_MISMATCH" in codes and "AMOUNT_MISMATCH" not in codes


def test_unknown_currency_is_reported():
    pos = load_pos()
    invoice = Invoice(vendor_name="Müller Elektronik GmbH", po_number="PO-2001", currency="XYZ", total=100)
    assert "UNSUPPORTED_CURRENCY" in {f.code for f in run_flags(invoice, match_invoice(invoice, pos))}
