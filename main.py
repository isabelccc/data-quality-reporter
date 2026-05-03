import io
import hashlib
import json
from typing import Any
import pandas as pd
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# In-memory cache: file hash → report
cache: dict[str, Any] = {}


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def analyze(df: pd.DataFrame) -> dict:
    report = {"row_count": len(df), "col_count": len(df.columns), "columns": {}}

    for col in df.columns:
        series = df[col]
        total = len(series)
        null_count = int(series.isna().sum())
        null_pct = round(null_count / total * 100, 1) if total > 0 else 0
        unique_count = int(series.nunique(dropna=True))
        duplicate_rows = int(total - series.nunique(dropna=False) - null_count)

        col_info: dict[str, Any] = {
            "dtype": str(series.dtype),
            "null_count": null_count,
            "null_pct": null_pct,
            "unique_count": unique_count,
            "issues": [],
        }

        # High nulls
        if null_pct > 30:
            col_info["issues"].append(f"High null rate: {null_pct}%")

        # Numeric analysis
        if pd.api.types.is_numeric_dtype(series):
            clean = series.dropna()
            if len(clean) > 0:
                mean = float(clean.mean())
                std = float(clean.std())
                col_info["mean"] = round(mean, 2)
                col_info["std"] = round(std, 2)
                col_info["min"] = float(clean.min())
                col_info["max"] = float(clean.max())

                # Outliers: values beyond 3 std devs
                if std > 0:
                    outliers = int(((clean - mean).abs() > 3 * std).sum())
                    col_info["outlier_count"] = outliers
                    if outliers > 0:
                        col_info["issues"].append(f"{outliers} outlier(s) beyond 3σ")

                # Distribution buckets for histogram
                counts, edges = np.histogram(clean, bins=10)
                col_info["histogram"] = {
                    "counts": counts.tolist(),
                    "edges": [round(float(e), 2) for e in edges],
                }

        # String analysis
        elif series.dtype == object:
            clean = series.dropna()
            if len(clean) > 0:
                # Mixed types check
                types_found = set(type(v).__name__ for v in clean)
                if len(types_found) > 1:
                    col_info["issues"].append(f"Mixed types: {types_found}")

                # Top values
                top = clean.value_counts().head(5)
                col_info["top_values"] = top.to_dict()

        if not col_info["issues"]:
            col_info["issues"] = []

        report["columns"][col] = col_info

    # Duplicate rows
    dup_rows = int(df.duplicated().sum())
    report["duplicate_rows"] = dup_rows
    if dup_rows > 0:
        report["top_issues"] = [f"{dup_rows} duplicate row(s) detected"]
    else:
        report["top_issues"] = []

    # Collect all column-level issues into top_issues
    for col, info in report["columns"].items():
        for issue in info["issues"]:
            report["top_issues"].append(f"[{col}] {issue}")

    return report


@app.post("/analyze")
async def analyze_file(file: UploadFile = File(...)):
    if not file.filename or not (
        file.filename.endswith(".csv") or file.filename.endswith(".json")
    ):
        raise HTTPException(status_code=400, detail="Only CSV and JSON files supported")

    data = await file.read()
    fhash = fingerprint(data)

    if fhash in cache:
        result = cache[fhash]
        result["cached"] = True
        return result

    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(data))
        else:
            df = pd.read_json(io.BytesIO(data))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {e}")

    report = analyze(df)
    report["filename"] = file.filename
    report["fingerprint"] = fhash[:12]
    report["cached"] = False

    cache[fhash] = report
    return report


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html") as f:
        return f.read()


app.mount("/static", StaticFiles(directory="static"), name="static")
