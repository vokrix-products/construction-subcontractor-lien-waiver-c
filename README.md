# WaiverGate Backend

**Product:** WaiverGate — a construction subcontractor lien waiver collection and payment-gate dashboard. It lets a buyer/general contractor track every subcontractor's and supplier's lien waiver status across projects, gate payment release on the completeness and validity of waivers, and stay ahead of deadlines with critical/warning status flags.

**Archetype:** Document ingestion and extraction core. WaiverGate ingests raw documents (PDFs, Excel workbooks, CSV exports, and plain text from sources like Procore, QuickBooks, Sage, or Xero) and normalizes them into structured records. When a `DEEPSEEK_API_KEY` is configured it uses DeepSeek for intelligent field extraction; otherwise it gracefully falls back to deterministic CSV/text extraction so the pipeline never breaks.

## Files

- processor.py — document ingestion and extraction core; defines `process_file(file_bytes: bytes) -> list[dict]`
- run_demo.py — smoke test using a hardcoded CSV byte string; zero args, exits 0
- run_tests.py — py_compile syntax check for all Python files in the repo root
- requirements.txt — Python dependencies (requests, openai, pdfplumber, openpyxl)

## What the poller expects as input

The poller (or any caller) sends raw `file_bytes` of one of these types:

- **PDF** — parsed with pdfplumber, page text extracted
- **Excel (.xlsx)** — parsed with openpyxl, cells flattened to tab-separated rows
- **CSV / TSV** — parsed deterministically; first line must contain the header row
- **Plain text (.txt)** — treated as CSV/text; if a header row with a delimiter is detected it is parsed row-by-row

Each returned record has exactly this shape:

```json
{
  "title": "Acme",
  "status": "not_required:good",
  "details": {"supplier": "Acme", "product": "Widget", "price": "9.99"},
  "due_date": null
}
```

- `title` — the primary entity tracked (subcontractor/supplier company name, otherwise project name)
- `status` — one of the allowed statuses with a severity suffix (`:good`, `:warning`, `:critical`), e.g. `signed:good`, `missing:critical`, `overdue:critical`, `requested:warning`
- `details` — all other extracted waiver/payment fields (invoice number, amounts, waiver period dates, signer info, notary info, e-signature envelope id, source system, etc.), snake_case keys
- `due_date` — ISO-8601 date or null, derived from any due/deadline column

Statuses without a recognized severity are normalized to `not_required:good`.

## Usage

```bash
python3 -m py_compile processor.py run_demo.py run_tests.py
python3 run_demo.py
python3 run_tests.py
```

To enable AI extraction, set `DEEPSEEK_API_KEY` in the environment before calling `process_file`.

Dashboard: https://construction-subcontractor-lien-waiver-c.vokrix.co
Vercel: construction-subcontractor-lien-waiver-c
