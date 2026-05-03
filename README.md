# Data Quality Reporter

A fast, local data quality analysis tool for CSV and JSON files. Upload a file and instantly get a full quality report — null rates, outliers, distributions, correlations, and an overall quality score.

Built as a Julius hackathon project to demonstrate what a **persistence layer outside ephemeral containers** could look like.

![screenshot](https://placehold.co/900x500/111118/7c6dfa?text=Data+Quality+Reporter)

---

## Features

- **Quality score** — single 0–100 score per file with letter grade
- **Per-column analysis** — nulls, unique count, mean, median, std, min, max, outliers
- **Visual histograms** — distribution chart for every numeric column
- **Top values** — frequency bar chart for string columns
- **Correlation matrix** — color-coded heatmap across all numeric columns
- **Issue detection** — flags high null rates, outliers beyond 3σ, mixed types, duplicate rows
- **Sample bad rows** — shows exact row numbers where issues occur
- **File fingerprint cache** — same file uploaded twice returns instantly (⚡ cached)
- **Export** — download full report as JSON
- **Sample data** — built-in messy dataset to demo instantly

---

## Quick Start

### 1. Clone
```bash
git clone https://github.com/isabelccc/data-quality-reporter.git
cd data-quality-reporter
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Open
```
http://localhost:8000
```

Drop any CSV or JSON file, or click **"Load sample messy data →"** to try the built-in dataset.

---

## Tech Stack

| Layer | Tool |
|-------|------|
| Backend | FastAPI (Python) |
| Data analysis | pandas, numpy |
| Frontend | Vanilla JS, HTML/CSS (no framework) |
| Server | Uvicorn |
| Caching | In-memory (SHA-256 file fingerprint) |

---

## Project Structure

```
data-quality-reporter/
├── main.py                  # FastAPI backend — analysis engine + API
├── requirements.txt
├── sample_data/
│   └── messy_sales.csv      # Demo dataset with intentional quality issues
└── static/
    └── index.html           # Frontend — drag-and-drop UI
```

---

## API

### `POST /analyze`
Upload a CSV or JSON file, get back a full quality report.

**Request:** `multipart/form-data` with `file` field

**Response:**
```json
{
  "filename": "sales.csv",
  "fingerprint": "a3f9c12d8e1b",
  "cached": false,
  "quality_score": 78,
  "row_count": 1000,
  "col_count": 8,
  "duplicate_rows": 3,
  "top_issues": [
    "[revenue] High null rate (18.0%)",
    "[age] 2 outlier(s) beyond 3σ"
  ],
  "columns": {
    "revenue": {
      "dtype": "float64",
      "null_count": 18,
      "null_pct": 18.0,
      "unique_count": 94,
      "mean": 142.5,
      "std": 88.2,
      "min": 0.0,
      "max": 9999.99,
      "outlier_count": 2,
      "histogram": { "counts": [...], "edges": [...] },
      "issues": ["High null rate (18.0%)", "2 outlier(s) beyond 3σ"],
      "sample_bad_rows": ["Row 10: value=9999.99"]
    }
  },
  "correlation": {
    "columns": ["age", "revenue"],
    "matrix": [[1.0, 0.43], [0.43, 1.0]]
  }
}
```

---

## The Julius Connection

Julius runs analysis in **ephemeral containers** — great for isolation and safety, but the workflow resets each session. This project demonstrates what a **persistence layer outside the container** would look like:

- File fingerprint → SHA-256 hash as cache key
- Same file = instant cached result, no recompute
- Full report exportable as JSON for reproducibility
- Correlation + quality score survive beyond the container lifecycle

This maps directly to the backend architecture described in [this design doc](https://julius.ai).

---

## Sample Data

`sample_data/messy_sales.csv` is an intentionally messy 20-row sales dataset with:
- Missing emails and ages
- An outlier revenue value ($9,999.99)
- A duplicate row
- An unrealistic age (999)

Perfect for demoing all issue-detection features.

---

## License

MIT
