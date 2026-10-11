"""Data models: the single source of truth for every shape in the project."""
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
Tier = Literal["critical", "supporting"]
Status = Literal["approve", "review", "reject"]


class Flag(BaseModel):
    code: str
    severity: Severity
    message: str
    tier: Tier = "critical"  # only critical flags may reject an invoice


class GateReport(BaseModel):
    """What the evidence gate concluded about one document."""
    grounded: bool = True
    verified: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    ignored_noise: list[str] = Field(default_factory=list)
    genuine_issues: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class InvoiceResult(BaseModel):
    filename: str
    file_hash: str
    invoice: Invoice
    po_found: bool = False
    po_total: Optional[float] = None
    po_currency: Optional[str] = None
    flags: list[Flag] = Field(default_factory=list)
    risk_score: int = 0
    status: Status = "approve"
    gate: Optional[GateReport] = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
