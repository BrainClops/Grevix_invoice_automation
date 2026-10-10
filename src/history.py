"""Pehle process hui invoices ka record (SQLite), duplicate pakadne ke liye."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "history.db"

_SCHEMA = """CREATE TABLE IF NOT EXISTS processed (
    file_hash TEXT, vendor_key TEXT, invoice_number TEXT,
    filename TEXT, total REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"""


def _connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute(_SCHEMA)
    return conn


def has_hash(db_path, file_hash: str) -> bool:
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT 1 FROM processed WHERE file_hash=? LIMIT 1", (file_hash,)).fetchone()
    return row is not None


def has_invoice_number(db_path, vendor_key: str, invoice_number: str, file_hash: str) -> bool:
    """Same vendor + same invoice number, par alag file."""
    if not invoice_number or not vendor_key:
        return False
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT 1 FROM processed WHERE vendor_key=? AND invoice_number=? AND file_hash!=? LIMIT 1",
            (vendor_key, invoice_number, file_hash),
        ).fetchone()
    return row is not None


def save(db_path, file_hash, vendor_key, invoice_number, filename, total) -> None:
    with closing(_connect(db_path)) as conn:
        conn.execute(
            "INSERT INTO processed (file_hash, vendor_key, invoice_number, filename, total) VALUES (?,?,?,?,?)",
            (file_hash, vendor_key, invoice_number, filename, total),
        )
        conn.commit()


def reset(db_path) -> None:
    with closing(_connect(db_path)) as conn:
        conn.execute("DELETE FROM processed")
        conn.commit()
