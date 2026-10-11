
"""Generate invoice PDF samples for demos and automated tests."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from reportlab.pdfgen import canvas


OUT = Path(__file__).resolve().parent.parent / "data" / "sample_invoices"


def make_invoice(
    path: Path,
    vendor: str,
    number: str,
    date: str,
    po: str,
    items: list[tuple[str, int, float]],
    subtotal: float,
    tax: float,
    total: float,
) -> None:
    """Generate a standard INR invoice PDF."""
    path.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(path))
    y = 800

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(50, y, "INVOICE")
    pdf.setFont("Helvetica", 11)

    for line in (
        f"Vendor: {vendor}",
        f"Invoice No: {number}",
        f"Invoice Date: {date}",
        f"PO Number: {po}",
        "Currency: INR",
    ):
        y -= 22
        pdf.drawString(50, y, line)

    y -= 36
    pdf.setFont("Courier", 10)
    pdf.drawString(
        50, y,
        f"{'Description':<28}{'Qty':>5}{'Unit Price':>14}{'Amount':>14}",
    )

    for description, quantity, price in items:
        y -= 18
        pdf.drawString(
            50, y,
            f"{description:<28}{quantity:>5}"
            f"{price:>14,.2f}{quantity * price:>14,.2f}",
        )

    pdf.setFont("Helvetica", 11)
    for label, value in (
        ("Subtotal", subtotal),
        ("Tax (18%)", tax),
        ("Total", total),
    ):
        y -= 24
        pdf.drawString(50, y, f"{label}: {value:,.2f}")

    pdf.save()


def make_international_invoice(
    path: Path,
    *,
    vendor: str,
    number: str,
    date: str,
    po: str,
    currency: str,
    subtotal_text: str,
    tax_text: str,
    total_text: str,
    note: str | None = None,
) -> None:
    """Generate an international invoice with locale-specific formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(path))
    y = 800

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(50, y, "INVOICE")
    pdf.setFont("Helvetica", 11)

    for line in (
        f"Vendor: {vendor}",
        f"Invoice No: {number}",
        f"Invoice Date: {date}",
        f"PO Number: {po}",
        f"Currency: {currency}",
    ):
        y -= 22
        pdf.drawString(50, y, line)

    if note:
        y -= 22
        pdf.drawString(50, y, note)

    y -= 36
    pdf.setFont("Helvetica", 11)

    for label, value in (
        ("Subtotal", subtotal_text),
        ("Tax", tax_text),
        ("Total", total_text),
    ):
        y -= 24
        pdf.drawString(50, y, f"{label}: {value}")

    pdf.save()


def build(out: Path = OUT) -> list[Path]:
    """Build all sample invoices and return their file paths."""
    out.mkdir(parents=True, exist_ok=True)

    stand = ("Laptop Stand", 10, 2500.0)
    arm = ("Monitor Arm", 10, 2500.0)

    clean = out / "01_clean.pdf"
    make_invoice(
        clean,
        "ABC Traders Pvt Ltd",
        "INV-1001",
        "2026-10-05",
        "PO-1001",
        [stand, arm],
        50000,
        9000,
        59000,
    )

    make_invoice(
        out / "02_amount_mismatch.pdf",
        "Sharma Electronics",
        "INV-2040",
        "2026-10-06",
        "PO-1002",
        [("LED Panel", 20, 4000.0), ("HDMI Cable", 100, 200.0)],
        100000,
        18000,
        118000,
    )

    shutil.copyfile(clean, out / "03_exact_duplicate.pdf")

    make_invoice(
        out / "04_unknown_vendor.pdf",
        "QuickFix Solutions",
        "QF-77",
        "2026-10-07",
        "PO-9999",
        [("Repair Service", 3, 5000.0)],
        16000,
        2700,
        18700,
    )

    make_invoice(
        out / "05_resubmitted_number.pdf",
        "ABC Traders Pvt Ltd",
        "INV-1001",
        "2026-10-09",
        "PO-1001",
        [stand, ("Monitor Arm", 10, 2700.0)],
        52000,
        9360,
        61360,
    )

    make_international_invoice(
        out / "07_german_eur.pdf",
        vendor="Müller Elektronik GmbH",
        number="ME-2026-100",
        date="08.10.2026",
        po="PO-2001",
        currency="EUR",
        subtotal_text="2.500,00",
        tax_text="475,00",
        total_text="2.975,00",
        note="Internal reference 123 - payment information only",
    )

    make_international_invoice(
        out / "08_us_usd.pdf",
        vendor="Global Office Supplies",
        number="US-2026-250",
        date="09/25/2026",
        po="PO-2002",
        currency="USD",
        subtotal_text="10,525.42",
        tax_text="1,894.58",
        total_text="12,420.00",
    )

    return sorted(out.glob("*.pdf"))


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT

    for file in build(target):
        print(f"Generated: {file}")

