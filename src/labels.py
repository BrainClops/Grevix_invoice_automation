"""Multilingual field labels and amount patterns shared by extraction and validation.

Label dictionaries cover English, German, French, Spanish and Italian. Only English
and German are exercised by the bundled sample invoices and tests.
"""
INVOICE_NO = (r"(?:invoice\s*(?:no\.?|number|#)|rechnungs(?:nummer|nr\.?)|rechnung\s*nr\.?"
              r"|facture\s*(?:n[°o]\.?|num[eé]ro)|n[uú]mero\s+de\s+factura|factura\s*(?:n[°o]\.?|num\.?)"
              r"|fattura\s*(?:n[°o]\.?|numero))")
VENDOR = r"(?:vendor|supplier|from|lieferant|fournisseur|proveedor|fornitore)"
PO = (r"(?:po\s*(?:no\.?|number)|bestell(?:nummer|-?nr\.?)|bon\s+de\s+commande"
      r"|orden\s+de\s+compra|ordine\s+d['’]acquisto)")
DATE = r"(?:invoice\s*date|rechnungsdatum|date\s+de\s+facture|fecha\s+de\s+factura|data\s+fattura)"
CURRENCY = r"(?:currency|währung|devise|moneda|valuta)"
SUBTOTAL = r"(?:sub\s*-?total|zwischensumme|sous-?total|imponibile)"
TAX = r"(?:tax|gst|vat|mwst\.?|ust\.?|tva|iva)"
TOTAL = (r"(?:(?:grand\s+|net\s+)?total(?:\s+(?:amount|due|payable))?(?:\s+ttc)?"
         r"|amount\s+(?:due|payable)|gesamtbetrag|gesamtsumme|endbetrag|montant\s+total|importe\s+total|totale)")

NUM = r"\d[\d.,'\u00a0\u202f]*"
CUR_PREFIX = r"(?:rs\.?|inr|usd|eur|gbp|jpy|aed|[$€£¥₹])?"
AMOUNT = rf"{CUR_PREFIX}\s*({NUM})"
AMOUNT_NAMED = rf"{CUR_PREFIX}\s*(?P<amt>{NUM})"
TAIL = r"(?:\s*\(.*\))?\s*(?:[A-Za-z]{3}|[$€£¥₹])?\s*$"
