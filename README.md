# Data Quality Reporter

> Upload a CSV or JSON file — get a full quality report in milliseconds.  
> Built for the **Julius Hackathon 2026** to demonstrate what a persistence + observability layer outside ephemeral containers could look like.

---

## What It Does

Most data analysis tools tell you *what* your data says. This tool tells you *what's wrong with it* before you analyze it.

Drop in any CSV or JSON file and instantly get:

- **Health score** (0–100) — single number summarizing overall data quality
- **Per-column profiling** — nulls, unique count, mean, median, std, min, max, outliers
- **Visual histograms** — distribution chart for every numeric column
- **Top value frequency** — bar chart for string/categorical columns
- **Issue detection** — flags high nulls, outliers beyond 3σ, mixed types, duplicate rows
- **Exact bad row pointers** — "Row 4: value=5000000.00" not just "outlier found"
- **Correlation heatmap** — color-coded matrix across all numeric columns
- **Pipeline timing** — shows ingest → parse → profile → assemble stages with ms per step
- **SHA-256 file fingerprint cache** — same file uploaded twice returns instantly (⚡ cached)
- **Export JSON** — download full report for reproducibility
- **✨ AI narrative** — one-click plain-English summary via Gemini 2.0 Flash (requires `GOOGLE_API_KEY`)

---

## Demo

**One click:** hit **⚡ Messy CRM** or **⚡ Messy Sales** on the homepage — no file needed.

The sample dataset has intentional problems:
- Duplicate rows
- Missing emails and revenue values
- A revenue outlier ($5,000,000 vs ~$50 avg)
- A mixed-type column (email column has a number `42`)
- Empty rows

The tool catches all of them and shows exactly where.

---

## Quick Start

### Requirements
- Python 3.10+

### Install & Run

```bash
git clone https://github.com/isabelccc/data-quality-reporter.git
cd data-quality-reporter

pip install -r requirements.txt

# Optional: enable AI narrative (Gemini)
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000**

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com/app/apikey) — the app runs fully without it.

---

## Tech Stack

| Layer | Tool | Why |
|-------|------|-----|
| Backend | FastAPI | Async, fast, automatic OpenAPI docs |
| Data analysis | pandas + numpy | Industry standard, handles CSV/JSON/large files |
| Server | Uvicorn | ASGI, production-grade |
| Frontend | Vanilla JS + HTML/CSS | No build step, instant load, zero dependencies |
| Fonts | DM Sans + Syne (Google Fonts) | Clean, modern, readable |
| Caching | In-memory dict (SHA-256 key) | Zero latency on repeat uploads |
| LLM | Gemini 2.0 Flash (optional) | Plain-English data quality narrative |

No database. No Docker required. Runs with just `pip install` — Gemini key is optional.

---

## Project Structure

```
data-quality-reporter/
├── main.py                     # FastAPI app — analysis engine + all API routes
├── requirements.txt            # 7 dependencies
├── .env.example                # Copy to .env and add GOOGLE_API_KEY for AI narrative
├── sample_data/
│   └── messy_sales.csv         # Demo dataset with intentional quality issues
└── static/
    └── index.html              # Full frontend — drag-and-drop UI, no framework
```

---

## How It Works

### The Pipeline

Every uploaded file goes through 4 timed stages:

```
┌──────────────────────────────────────────────────────────┐
│  Ingest      Read bytes · SHA-256 fingerprint · cache?   │  ~0.1 ms
│  Parse       pd.read_csv / pd.read_json · dtype infer    │  ~1–5 ms
│  Profile     Per-column stats · rules · correlation      │  ~2–10 ms
│  Assemble    Health score · severity · JSON response     │  ~0.02 ms
└──────────────────────────────────────────────────────────┘
```

The pipeline timing is shown in the UI so you can see exactly where time is spent.

### Health Score (0–100)

Starts at 100, deductions applied for:

| Issue | Penalty |
|-------|---------|
| Duplicate rows | up to −35 total |
| Null rate > 20% | −4 per column |
| Null rate > 40% | −10 per column |
| Null rate > 60% | −18 per column |
| Outlier detected | −3 per column |
| High null rate flag | −6 per column |
| Mixed types in column | −12 per column |

### File Fingerprint Cache

Every file is SHA-256 hashed on ingest. If you upload the same file again:

```
Upload → hash → cache hit → return instantly (⚡ cached badge shown)
```

This is the core demo of the Julius connection: **ephemeral execution, persistent results**.

### Outlier Detection

Uses the standard **3σ rule**:
- Compute mean and std of each numeric column (excluding nulls)
- Any value more than 3 standard deviations from the mean is flagged
- The exact row number and value are shown in the UI

### Correlation Matrix

For datasets with 2+ numeric columns:
- Compute Pearson correlation using pandas `.corr()`
- Render as color-coded heatmap
- Cyan = positive correlation, Rose = negative, darker = stronger

---

## API Reference

### `POST /analyze`

Upload a file for analysis.

**Request:** `multipart/form-data` with field `file` (`.csv` or `.json`)

**Response:**
```json
{
  "filename": "sales.csv",
  "fingerprint": "a3f9c12d8e1b4f2a",
  "cached": false,
  "health_score": 72,
  "severity": { "critical": 1, "warning": 3 },
  "row_count": 1000,
  "col_count": 8,
  "duplicate_rows": 2,
  "top_issues": [
    "2 duplicate row(s) detected",
    "[revenue] High null rate: 35.0%",
    "[age] 3 outlier(s) beyond 3σ"
  ],
  "columns": {
    "revenue": {
      "dtype": "float64",
      "null_count": 350,
      "null_pct": 35.0,
      "unique_count": 88,
      "mean": 142.5,
      "median": 120.0,
      "std": 88.2,
      "min": 0.0,
      "max": 9999.99,
      "outlier_count": 3,
      "histogram": { "counts": [...], "edges": [...] },
      "issues": ["High null rate: 35.0%", "3 outlier(s) beyond 3σ"],
      "sample_bad_rows": ["Row 4: value=9999.99", "Row 11: value=0.00"]
    }
  },
  "correlation": {
    "columns": ["age", "revenue"],
    "matrix": [[1.0, 0.43], [0.43, 1.0]]
  },
  "pipeline": [
    { "id": "ingest",        "label": "Ingest",          "ms": 0.08 },
    { "id": "parse",         "label": "Parse & types",   "ms": 3.21 },
    { "id": "profile_rules", "label": "Profile + rules", "ms": 7.44 },
    { "id": "report",        "label": "Assemble report", "ms": 0.02 }
  ],
  "pipeline_total_ms": 10.75
}
```

**Error responses:**
- `400` — unsupported file type
- `422` — malformed CSV/JSON

---

### `POST /api/narrative`

Generate a plain-English summary using Gemini 2.0 Flash. Requires `GOOGLE_API_KEY`.

**Request:** JSON body — the full report object returned by `/analyze`

**Response:** `{ "narrative": "Your dataset has 3 critical issues..." }`

---

### `GET /api/sample/messy-crm.csv`

Returns the built-in messy CRM demo dataset.

---

### `GET /api/sample/messy-sales.csv`

Returns the messy sales orders demo dataset.

---

### `GET /api/status`

Returns `{ "llm_enabled": true/false, "cached_reports": N }` — used by the frontend to show/hide the AI Summary button.

---

## The Julius Connection

Julius runs analysis inside **ephemeral containers** — great for isolation and safety, but the workflow resets between sessions. This project demonstrates the missing layer:

```
Container (ephemeral)          Persistence layer (this project)
─────────────────────          ────────────────────────────────
Run analysis             ───▶  Fingerprint file (SHA-256)
Generate output          ───▶  Cache report by fingerprint
Container dies           ───▶  Report survives, served instantly on re-upload
```

Concretely:
- **File fingerprint** = cache key → same file = same hash = instant result
- **Health score** = summarized output that persists outside the container
- **Pipeline JSON** = reproducible record of what ran and how long it took
- **Export** = full report downloadable as JSON for audit trail

The argument: keep execution ephemeral, make everything around it durable.

---



## License

MIT
