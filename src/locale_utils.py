"""Locale-aware parsing of amounts, dates and currencies.

Supported amount styles: 118,000.00 (US/UK), 1,18,000.00 (Indian), 118.000,00 (EU),
118'000.00 (Swiss) and non-breaking-space grouping. Known limits: a single dot followed
by exactly three digits is read as a thousands separator, and dd/mm versus mm/dd dates
are resolved by magnitude, defaulting to day-first when truly ambiguous.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

ISO_CODES = ("INR", "USD", "EUR", "GBP", "JPY", "AED", "SGD", "AUD", "CAD", "CHF")
_SYMBOLS = (("€", "EUR"), ("£", "GBP"), ("₹", "INR"), ("¥", "JPY"), ("$", "USD"))


def parse_amount(raw) -> Optional[float]:
    if raw is None:
        return None
    s = re.sub(r"[^\d.,'\u00a0\u202f\- ]", "", str(raw)).strip()
    negative = s.startswith("-")
    s = re.sub(r"[\s\u00a0\u202f']", "", s.lstrip("-")).strip(".,")
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):          # 118.000,00 -> European
            s = s.replace(".", "").replace(",", ".")
        else:                                    # 118,000.00 or 1,18,000.00
            s = s.replace(",", "")
    elif "," in s:
        tail = s.rpartition(",")[2]
        s = s.replace(",", ".") if (s.count(",") == 1 and len(tail) != 3) else s.replace(",", "")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3 and not s.startswith("0.")):
        s = s.replace(".", "")
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def normalize_date(raw: str) -> str:
    """Return YYYY-MM-DD when the date can be understood, else the original text."""
    s = raw.strip().strip(".")
    m = re.fullmatch(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", s)
        if m:
            a, b, y = map(int, m.groups())
            mo, d = (a, b) if (b > 12 and a <= 12) else (b, a)   # month-first only when forced
        else:
            for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"):
                try:
                    return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return s
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return s


def dates_in_text(text: str) -> set[str]:
    found = re.findall(r"\b\d{1,4}[./-]\d{1,2}[./-]\d{1,4}\b", text)
    return {normalize_date(token) for token in found}


def detect_currency(text: str, default: str = "INR") -> str:
    labelled = re.search(r"(?:currency|währung|devise|moneda|valuta)\s*[:\-]\s*([A-Za-z]{3})\b", text, re.I)
    if labelled and labelled.group(1).upper() in ISO_CODES:
        return labelled.group(1).upper()
    for symbol, code in _SYMBOLS:
        if symbol in text:
            return code
    if re.search(r"\brs\.?\s*\d", text, re.I):
        return "INR"
    for code in ISO_CODES:
        if re.search(rf"\b{code}\b", text):
            return code
    return default
