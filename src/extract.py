"""Step 2: Extract an ingested document into an Invoice.

Strategies:
  * Gemini API: extracts fields from invoice text or page images.
  * Offline: regex parser for text documents and local OCR for images.
  * Merge partial Gemini results with offline extraction.
  * Never silently treat a missing invoice total as a valid amount.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from . import labels as L
from .ingest import IngestedDoc
from .locale_utils import detect_currency, normalize_date, parse_amount
from .schema import Invoice, LineItem

MODEL = os.getenv("INVOICE_MODEL", "gemini-3.8-flash")

SYSTEM_PROMPT = (
    "You are a meticulous accounts-payable analyst. Extract invoice data "
    "and return exactly one JSON object without prose or markdown fences. "
    "Never invent missing values. Distinguish subtotal, tax, total, and "
    "amount due. Read the original invoice carefully. If a value is absent "
    "or unreadable, return null."
)

INSTRUCTION = """
Extract invoice information and return a JSON object with these keys:
{
  "invoice_number": string or null,
  "vendor_name": string or null,
  "po_number": string or null,
  "invoice_date": "YYYY-MM-DD" or null,
  "currency": ISO currency code or null,
  "subtotal": number or null,
  "tax": number or null,
  "total": number or null,
  "line_items": [
    {
      "description": string,
      "quantity": number,
      "unit_price": number,
      "amount": number
    }
  ]
}

Rules:
- Extract only values supported by the invoice.
- Never invent missing fields or amounts.
- Do not confuse an invoice number with a purchase-order number.
- Do not confuse subtotal, tax, total, balance due, and amount paid.
- Prefer the explicitly labelled final invoice total or grand total.
- Preserve negative amounts and decimal values.
- Use ISO currency codes such as INR, USD, EUR, or GBP.
- Use null for missing scalar values.
- Numbers must not contain currency symbols or thousands separators.
- Return valid JSON only.
"""


def llm_available() -> bool:
    """Check whether a Gemini API key is configured."""
    return bool(os.getenv("GEMINI_API_KEY"))


def _num(value: Any) -> Optional[float]:
    """Convert common invoice amount representations into numbers."""
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        import math

        result = float(value)
        return result if math.isfinite(result) else None

    try:
        result = parse_amount(str(value))
        if result is None:
            return None

        import math

        result = float(result)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _clean_text(value: Any) -> Optional[str]:
    """Return cleaned non-empty text, or None."""
    if value is None:
        return None

    result = str(value).strip()

    if not result or result.lower() in {
        "null",
        "none",
        "n/a",
        "not available",
        "unknown",
    }:
        return None

    return result


def _build_invoice(raw: dict[str, Any]) -> Invoice:
    """Validate extracted values and build the invoice schema."""
    items: list[LineItem] = []

    raw_items = raw.get("line_items") or []

    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue

            quantity = _num(item.get("quantity"))
            unit_price = _num(item.get("unit_price"))
            amount = _num(item.get("amount"))

            items.append(
                LineItem(
                    description=_clean_text(item.get("description")) or "",
                    quantity=quantity if quantity is not None else 0,
                    unit_price=(
                        unit_price if unit_price is not None else 0
                    ),
                    amount=amount if amount is not None else 0,
                )
            )

    invoice_date = _clean_text(raw.get("invoice_date"))

    if invoice_date:
        try:
            normalized = normalize_date(invoice_date)
            if normalized:
                invoice_date = normalized
        except (ValueError, TypeError):
            pass

    currency = (
        _clean_text(raw.get("currency")) or "INR"
    ).upper()

    # Do not replace a missing total with a guessed amount.
    # The schema currently requires a numeric total, so zero is retained
    # as a sentinel that rule_total() can flag for manual review.
    total = _num(raw.get("total"))

    return Invoice(
        invoice_number=_clean_text(raw.get("invoice_number")) or "",
        vendor_name=_clean_text(raw.get("vendor_name")) or "",
        po_number=_clean_text(raw.get("po_number")),
        invoice_date=invoice_date,
        currency=currency,
        subtotal=_num(raw.get("subtotal")),
        tax=_num(raw.get("tax")),
        total=total if total is not None else 0,
        line_items=items,
    )


def _parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON object, allowing surrounding markdown or prose."""
    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end <= start:
        raise ValueError("No JSON object found in Gemini response")

    result = json.loads(text[start:end + 1])

    if not isinstance(result, dict):
        raise ValueError("Gemini response must be a JSON object")

    return result


def _extract_with_llm(doc: IngestedDoc) -> dict[str, Any]:
    """Extract invoice fields through the Gemini API."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is missing. Set the key in your terminal."
        )

    client = genai.Client(api_key=api_key)

    if doc.kind == "text":
        contents = (
            f"Invoice text:\n\n{doc.text}\n\n{INSTRUCTION}"
        )
    else:
        images = getattr(doc, "images", None) or []

        if not images:
            raise ValueError(
                "No invoice page images are available for Gemini extraction."
            )

        contents = [
            f"Extract data from these invoice page images.\n{INSTRUCTION}"
        ]
        contents.extend(
            image.convert("RGB") for image in images[:5]
        )

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            max_output_tokens=3000,
        ),
    )

    return _parse_json(response.text or "")


_ITEM = re.compile(
    r"^(.+?)\s+(\d+(?:[.,]\d+)?)\s+"
    r"(\d[\d.,']*[.,]\d{2})\s+"
    r"(\d[\d.,']*[.,]\d{2})$"
)


def _find(pattern: str, text: str) -> Optional[str]:
    """Return the first capture group for a case-insensitive pattern."""
    try:
        match = re.search(pattern, text, re.I | re.M)
    except re.error:
        return None

    return match.group(1).strip() if match else None


def _find_amount(text: str, labels: list[str]) -> Optional[str]:
    """Find an amount following one of the supplied field labels."""
    for label in labels:
        # Prefer a field label at the beginning of a line.
        pattern = (
            rf"^\s*(?:{label})\s*"
            rf"(?:[:#\-]\s*|\s+)"
            rf"((?:₹|Rs\.?|INR|US\$|USD|EUR|€|GBP|£|\$)?\s*"
            rf"\(?-?\d[\d,.' ]*(?:\.\d{{1,4}})?\)?-?)"
            rf"\s*$"
        )

        value = _find(pattern, text)

        if value:
            parsed = _num(value)
            if parsed is not None:
                return value

        # Handle labels and amounts on the same line with extra text,
        # such as "Grand Total: INR 12,500.00".
        pattern = (
            rf"^\s*(?:{label})\s*[:#\-]\s*"
            rf"((?:₹|Rs\.?|INR|US\$|USD|EUR|€|GBP|£|\$)?\s*"
            rf"\(?-?\d[\d,.' ]*(?:\.\d{{1,4}})?\)?-?)"
            rf"(?:\s|$)"
        )

        value = _find(pattern, text)

        if value:
            parsed = _num(value)
            if parsed is not None:
                return value

    return None


def _extract_with_regex(text: str) -> dict[str, Any]:
    """Extract common labelled invoice fields without an API."""
    items: list[dict[str, Any]] = []

    for line in text.splitlines():
        match = _ITEM.match(line.strip())

        if match:
            items.append(
                {
                    "description": match.group(1),
                    "quantity": match.group(2),
                    "unit_price": match.group(3),
                    "amount": match.group(4),
                }
            )

    raw_date = _find(
        rf"{L.DATE}\s*[:#\-]\s*(\S.*)$",
        text,
    )

    try:
        invoice_date = normalize_date(raw_date) if raw_date else None
    except (ValueError, TypeError):
        invoice_date = raw_date

    currency = _find(
        rf"{L.CURRENCY}\s*[:#\-]\s*([A-Za-z]{{3}})",
        text,
    )

    invoice_number = _find(
        rf"{L.INVOICE_NO}\s*[:#\-]?\s*(\S+)",
        text,
    )

    vendor_name = _find(
        rf"^\s*{L.VENDOR}\s*[:#\-]\s*(.+)$",
        text,
    )

    po_number = _find(
        rf"\b{L.PO}\s*[:#\-]\s*(\S+)",
        text,
    )

    # Broader fallbacks help with common invoice templates.
    if not invoice_number:
        invoice_number = _find(
            r"^\s*(?:invoice\s*(?:no\.?|number|#|id))"
            r"\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/_\-]*)",
            text,
        )

    if not po_number:
        po_number = _find(
            r"^\s*(?:purchase\s*order|p\.?o\.?)"
            r"\s*(?:no\.?|number|#)?\s*[:#\-]\s*"
            r"([A-Z0-9][A-Z0-9/_\-]*)",
            text,
        )

    if not vendor_name:
        vendor_name = _find(
            r"^\s*(?:vendor\s*name|supplier\s*name|seller)"
            r"\s*[:#\-]\s*(.+?)\s*$",
            text,
        )

    # Match total-like labels separately. Do not let "Subtotal" match
    # the word "Total", and prefer Grand Total or Invoice Total.
    total_labels = [
        r"grand\s+total",
        r"invoice\s+total",
        r"total\s+due",
        r"amount\s+due",
        r"balance\s+due",
        r"total\s+payable",
        r"total\s+amount",
        r"total",
    ]

    subtotal_labels = [
        r"sub\s*total",
        r"subtotal",
        r"net\s+amount",
    ]

    tax_labels = [
        r"total\s+tax",
        r"tax\s+amount",
        r"gst\s+amount",
        r"vat\s+amount",
        r"tax",
        r"gst",
        r"vat",
    ]

    subtotal = _find_amount(text, subtotal_labels)
    tax = _find_amount(text, tax_labels)
    total = _find_amount(text, total_labels)

    # Legacy label patterns remain useful for project-specific aliases.
    if subtotal is None:
        subtotal = _find(
            rf"^\s*{L.SUBTOTAL}\s*[:#\-]?\s*{L.AMOUNT}",
            text,
        )

    if tax is None:
        tax = _find(
            rf"^\s*{L.TAX}[^:\n]*[:#\-]\s*{L.AMOUNT}",
            text,
        )

    if total is None:
        total = _find(
            rf"^\s*{L.TOTAL}\s*[:#\-]?\s*{L.AMOUNT}",
            text,
        )

    return {
        "invoice_number": invoice_number,
        "vendor_name": vendor_name,
        "po_number": po_number,
        "invoice_date": invoice_date,
        "currency": currency or detect_currency(text),
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "line_items": items,
    }


def _extract_with_ocr(doc: IngestedDoc) -> dict[str, Any]:
    """Read scanned invoices locally using RapidOCR."""
    try:
        import numpy as np
        from importlib import import_module

        RapidOCR = import_module(
            "rapidocr_onnxruntime"
        ).RapidOCR

    except ImportError as exc:
        raise ValueError(
            "Local OCR is not installed. Run: "
            "python -m pip install rapidocr-onnxruntime"
        ) from exc

    images = getattr(doc, "images", None) or []

    if not images:
        raise ValueError(
            "No page images are available for local OCR."
        )

    engine = RapidOCR()
    lines: list[str] = []

    for image in images:
        result, _elapsed = engine(
            np.asarray(image.convert("RGB"))
        )

        if result:
            for item in result:
                if len(item) >= 2 and item[1]:
                    lines.append(str(item[1]))

    text = "\n".join(lines).strip()

    if len(text) < 10:
        raise ValueError(
            "OCR could not read enough text from this invoice. "
            "Try a clearer, upright image or a text-based PDF."
        )

    return _extract_with_regex(text)


def _has_value(value: Any) -> bool:
    """Check whether a scalar extraction result is meaningfully present."""
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    return True


def _merge_extractions(
    primary: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """Fill missing Gemini fields from regex/OCR without overwriting values."""
    merged = dict(primary)

    scalar_fields = (
        "invoice_number",
        "vendor_name",
        "po_number",
        "invoice_date",
        "currency",
        "subtotal",
        "tax",
        "total",
    )

    for field in scalar_fields:
        if not _has_value(merged.get(field)) and _has_value(
            fallback.get(field)
        ):
            merged[field] = fallback[field]

    primary_items = merged.get("line_items")

    if not isinstance(primary_items, list) or not primary_items:
        fallback_items = fallback.get("line_items")
        if isinstance(fallback_items, list) and fallback_items:
            merged["line_items"] = fallback_items

    return merged


def extract_invoice(
    doc: IngestedDoc,
    use_llm: Optional[bool] = None,
) -> Invoice:
    """Extract invoice fields using Gemini and/or offline fallback."""
    use_llm = llm_available() if use_llm is None else use_llm

    if use_llm:
        try:
            llm_raw = _extract_with_llm(doc)

            # If Gemini returned a partial invoice, attempt to fill missing
            # values using the local text parser or OCR.
            try:
                if doc.kind == "text":
                    fallback_raw = _extract_with_regex(doc.text)
                else:
                    fallback_raw = _extract_with_ocr(doc)

                llm_raw = _merge_extractions(llm_raw, fallback_raw)

            except Exception as exc:
                print(
                    f"Offline supplemental extraction failed: {exc}"
                )

            return _build_invoice(llm_raw)

        except Exception as exc:
            print(
                f"Gemini extraction failed: {exc}. "
                "Trying offline extraction..."
            )

    if doc.kind == "text":
        return _build_invoice(_extract_with_regex(doc.text))

    return _build_invoice(_extract_with_ocr(doc))