import io
import hashlib
from typing import Any
import pandas as pd
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Data Quality Reporter")

cache: dict[str, Any] = {}


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_quality_score(df: pd.DataFrame, col_reports: dict) -> int:
    """0–100 score. Penalize nulls, outliers, duplicates, mixed types."""
    score = 100
    total = len(df)
    if total == 0:
        return 0

    # Duplicate rows: up to -20
    dup_pct = df.duplicated().sum() / total
    score -= min(20, int(dup_pct * 100))

    # Per-column penalties
    per_col = 80 / max(len(col_reports), 1)
    for info in col_reports.values():
        col_score = per_col
        # Nulls
        col_score -= min(per_col * 0.5, (info["null_pct"] / 100) * per_col)
        # Outliers
        if info.get("outlier_count", 0) > 0:
            outlier_pct = info["outlier_count"] / max(total - info["null_count"], 1)
            col_score -= min(per_col * 0.3, outlier_pct * per_col)
        # Issues
        col_score -= len(info["issues"]) * (per_col * 0.1)
        score -= (per_col - max(col_score, 0))

    return max(0, min(100, round(score)))


def analyze(df: pd.DataFrame) -> dict:
    total = len(df)
    columns: dict[str, Any] = {}

    for col in df.columns:
        series = df[col]
        null_count = int(series.isna().sum())
        null_pct = round(null_count / total * 100, 1) if total > 0 else 0.0
        unique_count = int(series.nunique(dropna=True))

        info: dict[str, Any] = {
            "dtype": str(series.dtype),
            "null_count": null_count,
            "null_pct": null_pct,
            "unique_count": unique_count,
            "issues": [],
            "sample_bad_rows": [],
        }

        # Flag null row indices (up to 3)
        null_idx = series[series.isna()].index.tolist()[:3]
        if null_idx:
            info["sample_bad_rows"] += [f"Row {i+2}: null value" for i in null_idx]

        if null_pct > 30:
            info["issues"].append(f"High null rate ({null_pct}%)")
        elif null_pct > 10:
            info["issues"].append(f"Moderate null rate ({null_pct}%)")

        if pd.api.types.is_numeric_dtype(series):
            clean = series.dropna()
            if len(clean) > 0:
                mean = float(clean.mean())
                std = float(clean.std())
                info.update({
                    "mean": round(mean, 2),
                    "std": round(std, 2),
                    "min": float(clean.min()),
                    "max": float(clean.max()),
                    "median": float(clean.median()),
                })
                if std > 0:
                    mask = (clean - mean).abs() > 3 * std
                    outlier_count = int(mask.sum())
                    info["outlier_count"] = outlier_count
                    if outlier_count > 0:
                        info["issues"].append(f"{outlier_count} outlier(s) beyond 3σ")
                        bad = clean[mask].index.tolist()[:3]
                        for i in bad:
                            info["sample_bad_rows"].append(f"Row {i+2}: value={clean[i]:.2f}")
                else:
                    info["outlier_count"] = 0

                counts, edges = np.histogram(clean, bins=10)
                info["histogram"] = {
                    "counts": counts.tolist(),
                    "edges": [round(float(e), 2) for e in edges],
                }
        else:
            clean = series.dropna()
            if len(clean) > 0:
                types_found = set(type(v).__name__ for v in clean)
                if len(types_found) > 1:
                    info["issues"].append(f"Mixed types detected: {', '.join(types_found)}")
                top = clean.value_counts().head(5)
                info["top_values"] = {str(k): int(v) for k, v in top.items()}

        columns[col] = info

    # Correlation matrix (numeric cols only)
    num_cols = df.select_dtypes(include="number").columns.tolist()
    correlation: dict[str, Any] = {}
    if len(num_cols) >= 2:
        corr = df[num_cols].corr().round(2)
        correlation = {
            "columns": num_cols,
            "matrix": corr.values.tolist(),
        }

    dup_rows = int(df.duplicated().sum())
    quality_score = compute_quality_score(df, columns)

    top_issues: list[str] = []
    if dup_rows > 0:
        top_issues.append(f"{dup_rows} duplicate row(s) detected")
    for col, info in columns.items():
        for issue in info["issues"]:
            top_issues.append(f"[{col}] {issue}")

    return {
        "row_count": total,
        "col_count": len(df.columns),
        "duplicate_rows": dup_rows,
        "quality_score": quality_score,
        "top_issues": top_issues,
        "columns": columns,
        "correlation": correlation,
    }


@app.post("/analyze")
async def analyze_file(file: UploadFile = File(...)):
    name = file.filename or ""
    if not (name.endswith(".csv") or name.endswith(".json")):
        raise HTTPException(status_code=400, detail="Only CSV and JSON files supported")

    data = await file.read()
    fhash = fingerprint(data)

    if fhash in cache:
        result = dict(cache[fhash])
        result["cached"] = True
        return result

    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(data))
        else:
            df = pd.read_json(io.BytesIO(data))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {e}")

    report = analyze(df)
    report["filename"] = name
    report["fingerprint"] = fhash[:12]
    report["cached"] = False
    cache[fhash] = report
    return report


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html") as f:
        return f.read()


app.mount("/static", StaticFiles(directory="static"), name="static")
