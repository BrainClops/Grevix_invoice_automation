from pathlib import Path
import shutil

root = Path.cwd()
extract_path = root / "src" / "extract.py"
requirements_path = root / "requirements.txt"

if not extract_path.exists() or not requirements_path.exists():
    raise SystemExit("Run this script from the invoice-automation project root.")

source = extract_path.read_text(encoding="utf-8")
old = '''def extract_invoice(doc: IngestedDoc, use_llm: Optional[bool] = None) -> Invoice:
    use_llm = llm_available() if use_llm is None else use_llm
    if use_llm:
        return _build_invoice(_extract_with_llm(doc))
    if doc.kind != "text":
        raise ValueError("Scanned invoices and photos require ANTHROPIC_API_KEY (vision extraction).")
    return _build_invoice(_extract_with_regex(doc.text))
'''
new = '''def _extract_with_ocr(doc: IngestedDoc) -> dict[str, Any]:
    # Local OCR for scanned PDFs and invoice photos; no paid vision API needed.
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise ValueError(
            "Local OCR is not installed. Run: python -m pip install rapidocr-onnxruntime"
        ) from exc

    engine = RapidOCR()
    lines: list[str] = []
    for image in doc.images:
        result, _elapsed = engine(np.asarray(image.convert("RGB")))
        if result:
            for item in result:
                # RapidOCR items contain bounding box, recognized text, confidence.
                if len(item) >= 2 and item[1]:
                    lines.append(str(item[1]))
    text = "\n".join(lines).strip()
    if len(text) < 10:
        raise ValueError(
            "OCR could not read enough text from this invoice. Try a clearer, "
            "upright image or a text-based PDF."
        )
    return _extract_with_regex(text)


def extract_invoice(doc: IngestedDoc, use_llm: Optional[bool] = None) -> Invoice:
    use_llm = llm_available() if use_llm is None else use_llm
    if use_llm:
        return _build_invoice(_extract_with_llm(doc))
    if doc.kind == "image":
        return _build_invoice(_extract_with_ocr(doc))
    return _build_invoice(_extract_with_regex(doc.text))
'''
if old not in source:
    raise SystemExit("Expected function was not found. No files were changed.")

shutil.copy2(extract_path, extract_path.with_suffix(".py.bak"))
shutil.copy2(requirements_path, requirements_path.with_suffix(".txt.bak"))
extract_path.write_text(source.replace(old, new, 1), encoding="utf-8")

requirements = requirements_path.read_text(encoding="utf-8")
if "rapidocr-onnxruntime" not in requirements.lower():
    requirements = requirements.rstrip() + "\\nrapidocr-onnxruntime>=1.3.24\\n"
requirements_path.write_text(requirements, encoding="utf-8")

print("Local OCR support added.")
print("Backups: src/extract.py.bak and requirements.txt.bak")
print("Next: python -m pip install -r requirements.txt")
print("Then: python -m pytest -v")