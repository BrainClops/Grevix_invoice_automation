"""Step 2: Extract. Turn an ingested document into a validated Invoice.

Two strategies share one contract:
  * LLM mode  - Claude reads text or page images and returns strict JSON.
  * Offline   - a deterministic regex parser for text PDFs with labelled fields,
                so the demo still works without an API key or network access.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from typing import Any, Optional

from .ingest import IngestedDoc
from .schema import Invoice, LineItem

MODEL = os.getenv("INVOICE_MODEL", "claude-sonnet-5-5")

SYSTEM_PROMPT = (
    "You are a meticulous accounts-payable analyst. Extract invoice data and reply with "
    "exactly one JSON object, no prose, no markdown fences."
)
INSTRUCTION = (
    "Return JSON with keys: invoice_number, vendor_name, po_number, invoice_date (YYYY-MM-DD), "
    "currency (ISO code), subtotal, tax, total, line_items (list of {description, quantity, "
    "unit_price, amount}). Use null when a field is absent. Numbers must be plain numerics "
    "with no currency symbols or thousands separators. Never invent values."
)


def llm_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(re.sub(r"[^\d.\-]", "", str(value)))
    except ValueError:
        return None


def _build_invoice(raw: dict[str, Any]) -> Invoice:
    items = [
        LineItem(
            description=str(i.get("description") or ""),
            quantity=_num(i.get("quantity")) or 0,
            unit_price=_num(i.get("unit_price")) or 0,
            amount=_num(i.get("amount")) or 0,
        )
        for i in (raw.get("line_items") or [])
    ]
    return Invoice(
        invoice_number=str(raw.get("invoice_number") or "").strip(),
        vendor_name=str(raw.get("vendor_name") or "").strip(),
        po_number=(str(raw["po_number"]).strip() if raw.get("po_number") else None),
        invoice_date=(str(raw["invoice_date"]).strip() if raw.get("invoice_date") else None),
        currency=str(raw.get("currency") or "INR").upper(),
        subtotal=_num(raw.get("subtotal")),
        tax=_num(raw.get("tax")),
        total=_num(raw.get("total")) or 0,
        line_items=items,
    )


def _parse_json(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model reply")
    return json.loads(text[start : end + 1])


def _image_block(image) -> dict[str, Any]:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = base64.b64encode(buffer.getvalue()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}


def _extract_with_llm(doc: IngestedDoc) -> dict[str, Any]:
    import anthropic  # imported lazily so offline mode needs no SDK

    if doc.kind == "text":
        content = [{"type": "text", "text": f"Invoice text:\n\n{doc.text}\n\n{INSTRUCTION}"}]
    else:
        content = [_image_block(img) for img in doc.images[:5]]
        content.append({"type": "text", "text": INSTRUCTION})

    client = anthropic.Anthropic()
    last_error: Exception | None = None
    for _ in range(2):  # one retry covers the rare malformed reply
        reply = client.messages.create(
            model=MODEL, max_tokens=2000, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(b.text for b in reply.content if getattr(b, "type", "") == "text")
        try:
            return _parse_json(text)
        except ValueError as exc:
            last_error = exc
    raise ValueError(f"Model did not return valid JSON: {last_error}")


_AMOUNT = r"(?:rs\.?|inr|usd|\$|₹)?\s*([\d,]+(?:\.\d+)?)"
_ITEM = re.compile(r"^(.+?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$")


def _find(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, re.I | re.M)
    return match.group(1).strip() if match else None


def _extract_with_regex(text: str) -> dict[str, Any]:
    items = []
    for line in text.splitlines():
        m = _ITEM.match(line.strip())
        if m:
            items.append({"description": m[1], "quantity": m[2], "unit_price": m[3], "amount": m[4]})
    return {
        "invoice_number": _find(r"invoice\s*(?:no\.?|number|#)\s*[:\-]?\s*(\S+)", text),
        "vendor_name": _find(r"^\s*(?:vendor|supplier|from)\s*[:\-]\s*(.+)$", text),
        "po_number": _find(r"\bpo\s*(?:no\.?|number)\s*[:\-]\s*(\S+)", text),
        "invoice_date": _find(r"invoice\s*date\s*[:\-]\s*(\S.*)$", text),
        "currency": _find(r"currency\s*[:\-]\s*([A-Za-z]{3})", text),
        "subtotal": _find(rf"^\s*sub\s*-?total\s*[:\-]?\s*{_AMOUNT}", text),
        "tax": _find(rf"^\s*(?:tax|gst)[^:\n]*[:\-]\s*{_AMOUNT}", text),
        "total": _find(rf"^\s*(?:grand\s+)?total(?:\s+amount)?\s*[:\-]?\s*{_AMOUNT}", text),
        "line_items": items,
    }


def extract_invoice(doc: IngestedDoc, use_llm: Optional[bool] = None) -> Invoice:
    use_llm = llm_available() if use_llm is None else use_llm
    if use_llm:
        return _build_invoice(_extract_with_llm(doc))
    if doc.kind != "text":
        raise ValueError("Scanned invoices and photos require ANTHROPIC_API_KEY (vision extraction).")
    return _build_invoice(_extract_with_regex(doc.text))
