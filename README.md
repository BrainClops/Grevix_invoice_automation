# LedgerLens

Autonomous accounts-payable intelligence: every invoice is read, reconciled against its purchase order, and cross-examined for duplication, drift and fraud before a single rupee leaves the building.

## The problem

Finance teams at large enterprises adjudicate thousands of invoices a month by hand. The work is slow, monotonous and error-prone, and the errors are costly: duplicate payments, inflated totals and phantom vendors routinely slip past a tired reviewer.

## The solution

LedgerLens converts that ritual into a five-stage pipeline. Humans are summoned only for the invoices that genuinely deserve scrutiny.

| Stage | Module | Responsibility |
|---|---|---|
| 1. Ingest | `src/ingest.py` | Validate the upload, extract PDF text, rasterise scans, fingerprint with SHA-256 |
| 2. Extract | `src/extract.py` | Claude (text or vision) returns strict JSON; an offline regex parser is the fallback |
| 3. Match | `src/match.py` | Reconcile against `data/purchase_orders.csv` with fuzzy vendor matching |
| 4. Flag | `src/flags.py` | Pluggable rule engine producing severity-weighted flags and a 0-100 risk score |
| 5. Verdict | `web/index.html` | Interactive 3D console: approve, review or reject, with evidence |

Verdict policy: any high-severity flag rejects, any other flag routes to review, a clean invoice is approved.

### Controls shipped

`DUPLICATE_FILE` · `DUPLICATE_INVOICE_NUMBER` · `PO_NOT_FOUND` · `NO_PO_NUMBER` · `UNKNOWN_VENDOR` · `VENDOR_MISMATCH` · `AMOUNT_MISMATCH` (>2% medium, >10% high) · `LINE_ITEMS_MISMATCH` · `TOTAL_MATH_ERROR` · `FUTURE_DATE`

## Run it

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --reload
```

Open <http://127.0.0.1:8000> and press **Run the demo corpus**.

For vision extraction of scanned invoices and photographs, export `ANTHROPIC_API_KEY` (see `.env.example`). Without it the offline engine handles text PDFs with labelled fields.

```bash
python -m pytest        # end-to-end tests over the generated corpus
```

## Architecture

```
web/index.html  --HTTP-->  server.py (FastAPI)
                              |
                              v
                    src/pipeline.py -> ingest -> extract -> match -> flags
                              |
                              v
                    src/history.py (SQLite: duplicate memory)
```

Each stage is an isolated module behind a typed contract (`src/schema.py`). Adding a control means writing one function and appending it to `RULES` in `src/flags.py`; swapping the extractor never touches the rest of the system.

## Roadmap

Multi-currency normalisation, three-way match against goods receipts, ERP connectors, and a learned anomaly model over vendor payment history.
