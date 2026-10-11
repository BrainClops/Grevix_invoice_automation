from pathlib import Path

path = Path("src/flags.py")
text = path.read_text(encoding="utf-8")

swaps = [
    ("Ye exact same file pehle process ho chuki hai.", "This exact file has already been processed."),
    ("is vendor se pehle aa chuka hai (alag file).", "was already submitted by this vendor in a different file."),
    ("Invoice par PO number nahi hai.", "No PO number appears on the invoice."),
    ("database mein nahi mila.", "was not found in the purchase-order database."),
    ("approved list mein nahi hai.", "is not on the approved vendor list."),
    ("hai, par PO vendor '{m.po_vendor}' hai.", "differs from the PO vendor '{m.po_vendor}'."),
    ("Invoice total {inv.total:,.2f} hai, PO approved total", "Invoice total {inv.total:,.2f} versus approved PO total"),
    ("(farq {diff", "(variance {diff"),
    ("Line items ka sum {items_sum:,.2f} hai, par subtotal {inv.subtotal:,.2f} likha hai.",
     "Line items sum to {items_sum:,.2f}, but the stated subtotal is {inv.subtotal:,.2f}."),
    ("Subtotal + tax, total ke barabar nahi hai.", "Subtotal plus tax does not equal the stated total."),
    ("Invoice date samajh nahi aayi.", "The invoice date could not be parsed."),
    ("aaj se aage ki hai.", "lies in the future."),
]

for old, new in swaps:
    if old not in text:
        raise SystemExit(f"NOT FOUND: {old}")
    text = text.replace(old, new)

path.write_text(text, encoding="utf-8")
print(f"Done: {len(swaps)} messages translated.")