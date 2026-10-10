"""LedgerLens API. Run with:  uvicorn server:app --reload"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, UploadFile
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from src import history
from src.extract import llm_available
from src.match import load_pos
from src.pipeline import process

WEB_DIR = Path(__file__).parent / "web"
app = FastAPI(title="LedgerLens", version="1.0.0")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "mode": "llm" if llm_available() else "offline"}


@app.post("/api/process")
async def process_invoices(files: list[UploadFile]) -> dict:
    pos = load_pos()
    results, errors = [], []
    for upload in files:
        payload = await upload.read()
        try:
            result = await run_in_threadpool(process, payload, upload.filename, pos)
            results.append(result.model_dump())
        except Exception as exc:  # one bad file must not sink the batch
            errors.append({"filename": upload.filename, "error": str(exc)})
    return {"results": results, "errors": errors}


@app.post("/api/demo")
async def run_demo() -> dict:
    """One-click showcase: push the bundled, deliberately flawed corpus through the pipeline."""
    from scripts.make_samples import OUT, build

    history.reset(history.DEFAULT_DB)
    pos, results, errors = load_pos(), [], []
    for path in build(OUT):
        try:
            result = await run_in_threadpool(process, path, path.name, pos)
            results.append(result.model_dump())
        except Exception as exc:
            errors.append({"filename": path.name, "error": str(exc)})
    return {"results": results, "errors": errors}


@app.post("/api/reset")
def reset_history() -> dict:
    history.reset(history.DEFAULT_DB)
    return {"status": "cleared"}


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
