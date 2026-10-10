"""Generate a small, deliberately flawed invoice corpus for demos and tests."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "data" / "sample_invoices"


def make_invoice(path: Path, vendor, number, date, po, items, subtotal, tax, total) -> None:
    pdf = canvas.Canvas(str(path))
    y = 800
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(50, y, "INVOICE")
    pdf.setFont("Helvetica", 11)
    for line in (f"Vendor: {vendor}", f"Invoice No: {number}", f"Invoice Date: {date}",
                 f"PO Number: {po}", "Currency: INR"):
        y -= 22
        pdf.drawString(50, y, line)
    y -= 36
    pdf.setFont("Courier", 10)
    pdf.drawString(50, y, f"{'Description':<28}{'Qty':>5}{'Unit Price':>14}{'Amount':>14}")
    for desc, qty, price in items:
        y -= 18
        pdf.drawString(50, y, f"{desc:<28}{qty:>5}{price:>14,.2f}{qty * price:>14,.2f}")
    pdf.setFont("Helvetica", 11)
    for label, value in (("Subtotal", subtotal), ("Tax (18%)", tax), ("Total", total)):
        y -= 24
        pdf.drawString(50, y, f"{label}: {value:,.2f}")
    pdf.save()


def build(out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    stand, arm = ("Laptop Stand", 10, 2500.0), ("Monitor Arm", 10, 2500.0)
    clean = out / "01_clean.pdf"
    make_invoice(clean, "ABC Traders Pvt Ltd", "INV-1001", "2026-10-05", "PO-1001",
                 [stand, arm], 50000, 9000, 59000)
    make_invoice(out / "02_amount_mismatch.pdf", "Sharma Electronics", "INV-2040", "2026-10-06", "PO-1002",
                 [("LED Panel", 20, 4000.0), ("HDMI Cable", 100, 200.0)], 100000, 18000, 118000)
    shutil.copyfile(clean, out / "03_exact_duplicate.pdf")
    make_invoice(out / "04_unknown_vendor.pdf", "QuickFix Solutions", "QF-77", "2026-10-07", "PO-9999",
                 [("Repair Service", 3, 5000.0)], 16000, 2700, 18700)
    make_invoice(out / "05_resubmitted_number.pdf", "ABC Traders Pvt Ltd", "INV-1001", "2026-10-09", "PO-1001",
                 [stand, ("Monitor Arm", 10, 2700.0)], 52000, 9360, 61360)
    return sorted(out.glob("*.pdf"))


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    for file in build(target):
        print("wrote", file)
