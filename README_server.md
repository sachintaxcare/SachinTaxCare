# SachinTaxCare — Filing Server

## What this is

A Flask server that connects the browser intake form (`sachintaxcare_intake.html`)
to the real Python computation engine (`sachintaxcare_engine.py`).

Previously the intake called the Anthropic API and asked Claude to compute the
return. This server replaces that with `sachintaxcare_engine.run(schema)` — the
180-test, IRS-verified Python engine. Computation is deterministic, citable, and
does not depend on an API key.

## Files

| File | Purpose |
|---|---|
| `sachintaxcare_server.py` | Flask server — /compute endpoint |
| `sachintaxcare_engine.py` | 7,641-line computation engine (v15) |
| `sachintaxcare_intake.html` | 13-section browser intake form |
| `sachintaxcare_workpaper.html` | 4-page print-quality workpaper |
| `requirements.txt` | Python dependencies |

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python3 sachintaxcare_server.py
```

Then open:
- **http://localhost:5000** — intake form (all 13 sections)
- **http://localhost:5000/workpaper** — workpaper renderer
- **http://localhost:5000/health** — engine health check

## Workflow

1. Open **http://localhost:5000**
2. Fill in the 13 intake sections (taxpayer → income → deductions → credits → retirement)
3. Click **⚡ Compute Return** — POST /compute calls the real engine
4. Review the inline result (AGI, taxable income, total tax, refund/owe, warnings)
5. Click **📄 Open Workpaper PDF** — opens the 4-page workpaper
6. Click **🖨 Print / Save PDF** — browser prints to PDF (letter format, 0.6in margins)

## API

### POST /compute

Request:
```json
{ "schema": { ...TaxpayerSchema JSON... } }
```

Response:
```json
{
  "result": {
    "agi": 95850,
    "taxable_income": 68850,
    "income_tax": 10061,
    "l24_total_tax": 8061,
    "l34_refund": 5939,
    "l37_owe": 0,
    "effective_rate": 0.084,
    "marginal_rate": 0.22,
    "warnings": ["...IRS-cited notice..."],
    ...all Form 1040 lines...
  },
  "engine_version": "v15",
  "test_counts": { "engine": 180, "report": 52 }
}
```

## Deploy (optional)

For production access beyond localhost, set environment variables:

```bash
HOST=0.0.0.0 PORT=8080 DEBUG=0 python3 sachintaxcare_server.py
```

Or use gunicorn:

```bash
pip install gunicorn
gunicorn sachintaxcare_server:app --bind 0.0.0.0:8080 --workers 2
```

## Architecture

```
Browser (intake.html)
  → POST /compute { schema: {...} }

sachintaxcare_server.py
  → deserialize_schema(dict) → TaxpayerSchema
  → sachintaxcare_engine.run(schema) → result["computed"]
  → map_result(engine_result) → flat JSON
  ← { result: {...}, warnings: [...] }

Browser renders inline result
Browser opens workpaper.html
  ← reads result from localStorage
  ← renders 4-page Form 1040 workpaper
  ← window.print() → PDF
```

## What changed from the old widget

The old widget (`sachintaxcare_widget.html`) sent a 1,663-line text prompt to
the Anthropic API and asked Claude to compute and format the entire return.

The new system:
- Uses the deterministic Python engine for all arithmetic
- Claude is not in the computation path
- Results are reproducible across runs
- Every number traces to a specific IRS form and test case
- The workpaper renders engine output directly, not Claude's text response
