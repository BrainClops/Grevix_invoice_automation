"""Data models: poore project mein ek hi jagah jahan shape define hoti hai."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = ""
    quantity: float = 0
    unit_price: float = 0
    amount: float = 0


class Invoice(BaseModel):
    invoice_number: str = ""
    vendor_name: str = ""
    po_number: Optional[str] = None
    invoice_date: Optional[str] = None  # YYYY-MM-DD
    currency: str = "INR"
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: float = 0
    line_items: list[LineItem] = Field(default_factory=list)


Severity = Literal["low", "medium", "high"]
Status = Literal["approve", "review", "reject"]


class Flag(BaseModel):
    code: str
    severity: Severity
    message: str


class InvoiceResult(BaseModel):
    filename: str
    file_hash: str
    invoice: Invoice
    po_found: bool = False
    po_total: Optional[float] = None
    flags: list[Flag] = Field(default_factory=list)
    risk_score: int = 0
    status: Status = "approve"
