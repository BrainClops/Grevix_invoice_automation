"""Step 1: Upload / Ingest.

Kaam: invoice file (PDF ya image) lena aur use aise format mein dena
jo agla step (extract.py) seedha use kar sake.

Output hamesha ek IngestedDoc hota hai:
  - text   : agar PDF mein selectable text hai
  - images : agar scanned PDF ya photo hai (LLM vision / OCR ke liye)
  - file_hash : duplicate invoice pakadne ke kaam aayega (flags.py)
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from PIL import Image

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_FILE_MB = 10
MIN_TEXT_CHARS = 30  # isse kam text mila to PDF scanned maan lo


@dataclass
class IngestedDoc:
    filename: str
    file_hash: str
    kind: str                       # "text" ya "image"
    text: str = ""
    images: list[Image.Image] = field(default_factory=list)


def _read_bytes(source, filename: str | None) -> tuple[bytes, str]:
    """Path, bytes, ya Streamlit UploadedFile: teeno ko handle karta hai."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        return path.read_bytes(), path.name
    if isinstance(source, bytes):
        return source, filename or "uploaded_file"
    # Streamlit UploadedFile / file-like object
    data = source.getvalue() if hasattr(source, "getvalue") else source.read()
    return data, filename or getattr(source, "name", "uploaded_file")


def _validate(data: bytes, filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"'{ext}' supported nahi hai. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
    if len(data) == 0:
        raise ValueError("File khali hai.")
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise ValueError(f"File {MAX_FILE_MB} MB se badi hai.")


def _ingest_pdf(data: bytes, filename: str, file_hash: str) -> IngestedDoc:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages).strip()

        if len(text) >= MIN_TEXT_CHARS:
            return IngestedDoc(filename, file_hash, kind="text", text=text)

        # Scanned PDF: pages ko images bana do
        images = [page.to_image(resolution=200).original for page in pdf.pages]
        return IngestedDoc(filename, file_hash, kind="image", images=images)


def _ingest_image(data: bytes, filename: str, file_hash: str) -> IngestedDoc:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    return IngestedDoc(filename, file_hash, kind="image", images=[image])


def ingest(source, filename: str | None = None) -> IngestedDoc:
    data, name = _read_bytes(source, filename)
    _validate(data, name)
    file_hash = hashlib.sha256(data).hexdigest()

    if Path(name).suffix.lower() == ".pdf":
        return _ingest_pdf(data, name, file_hash)
    return _ingest_image(data, name, file_hash)


if __name__ == "__main__":
    import sys

    doc = ingest(sys.argv[1])
    print(f"File : {doc.filename}")
    print(f"Type : {doc.kind}")
    print(f"Hash : {doc.file_hash[:12]}...")
    if doc.kind == "text":
        print("--- text preview ---")
        print(doc.text[:500])
    else:
        print(f"Images: {len(doc.images)} page(s)")
