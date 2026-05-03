"""
Data Quality Reporter — FastAPI backend.
Pipeline: Ingest → Parse → Profile + rules → Correlate → Assemble.
"""
from __future__ import annotations
import io, hashlib, time
from typing import Any
import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Data Quality Reporter", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

cache: dict[str, Any] = {}

def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _health_score(report: dict) -> int:
    score = 100
    score -= min(35, (report.get("duplicate_rows") or 0) * 3)
    for info in report.get("columns", {}).values():
        npct = info.get("null_pct") or 0
        if npct > 60: score -= 18
        elif npct > 40: score -= 10
        elif npct > 20: score -= 4
        for iss in info.get("issues") or []:
            low = iss.lower()
            if "mixed" in low: score -= 12
            elif "outlier" in low: score -= 3
            elif "high null" in low: score -= 6
    return max(0, min(100, int(round(score))))

def _severity_counts(report: dict) -> dict:
    critical, warn = 0, 0
    if (report.get("duplicate_rows") or 0) > 0: warn += 1
    for info in report.get("columns", {}).values():
        for iss in info.get("issues") or []:
            low = iss.lower()
            if "mixed" in low or ("high null" in low and (info.get("null_pct") or 0) > 50):
                critical += 1
            else: warn += 1
    return {"critical": critical, "warning": warn}

def analyze(df: pd.DataFrame) -> dict:
    total = len(df)
    columns: dict[str, Any] = {}

    for col in df.columns:
        series = df[col]
        null_count = int(series.isna().sum())
        null_pct = round(null_count / total * 100, 1) if total > 0 else 0.0
        info: dict[str, Any] = {
            "dtype": str(series.dtype),
            "null_count": null_count,
            "null_pct": null_pct,
            "unique_count": int(series.nunique(dropna=True)),
            "issues": [],
            "sample_bad_rows": [],
        }
        null_idx = series[series.isna()].index.tolist()[:3]
        if null_idx:
            info["sample_bad_rows"] += [f"Row {i+2}: null value" for i in null_idx]
        if null_pct > 30: info["issues"].append(f"High null rate: {null_pct}%")
        elif null_pct > 10: info["issues"].append(f"Moderate null rate: {null_pct}%")

        if pd.api.types.is_numeric_dtype(series):
            clean = series.dropna()
            if len(clean) > 0:
                mean, std = float(clean.mean()), float(clean.std()) if len(clean) > 1 else 0.0
                info.update({"mean": round(mean,4), "std": round(std,4),
                              "min": float(clean.min()), "max": float(clean.max()),
                              "median": float(clean.median())})
                if std > 0:
                    mask = (clean - mean).abs() > 3 * std
                    oc = int(mask.sum())
                    info["outlier_count"] = oc
                    if oc > 0:
                        info["issues"].append(f"{oc} outlier(s) beyond 3σ")
                        for i in clean[mask].index.tolist()[:3]:
                            info["sample_bad_rows"].append(f"Row {i+2}: value={clean[i]:.2f}")
                else:
                    info["outlier_count"] = 0
                counts, edges = np.histogram(clean.astype(float), bins=10)
                info["histogram"] = {"counts": [int(x) for x in counts],
                                     "edges": [round(float(e),4) for e in edges]}
        elif series.dtype == object:
            clean = series.dropna()
            if len(clean) > 0:
                types_found = {type(v).__name__ for v in clean.head(500)}
                if len(types_found) > 1:
                    info["issues"].append(f"Mixed types: {types_found}")
                top = clean.astype(str).value_counts().head(5)
                info["top_values"] = {str(k): int(v) for k, v in top.items()}

        columns[str(col)] = info

    num_cols = df.select_dtypes(include="number").columns.tolist()
    correlation: dict[str, Any] = {}
    if len(num_cols) >= 2:
        corr = df[num_cols].corr().round(3)
        correlation = {"columns": num_cols, "matrix": corr.values.tolist()}

    dup_rows = int(df.duplicated().sum())
    report: dict[str, Any] = {
        "row_count": total, "col_count": len(df.columns),
        "columns": columns, "duplicate_rows": dup_rows,
        "correlation": correlation, "top_issues": [],
    }
    if dup_rows > 0:
        report["top_issues"].append(f"{dup_rows} duplicate row(s) detected")
    for col, info in columns.items():
        for issue in info["issues"]:
            report["top_issues"].append(f"[{col}] {issue}")
    report["health_score"] = _health_score(report)
    report["severity"] = _severity_counts(report)
    return report


@app.post("/analyze")
async def analyze_file(file: UploadFile = File(...)):
    name = file.filename or ""
    if not (name.endswith(".csv") or name.endswith(".json")):
        raise HTTPException(status_code=400, detail="Only CSV and JSON files supported")

    t0 = time.perf_counter()
    raw = await file.read()
    ingest_ms = (time.perf_counter() - t0) * 1000
    fhash = fingerprint(raw)

    if fhash in cache:
        result = dict(cache[fhash]); result["cached"] = True; return result

    size_kb = round(len(raw) / 1024, 3)
    t_parse = time.perf_counter()
    try:
        df = pd.read_csv(io.BytesIO(raw)) if name.endswith(".csv") else pd.read_json(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {e}") from e
    parse_ms = (time.perf_counter() - t_parse) * 1000

    t_analyze = time.perf_counter()
    report = analyze(df)
    analyze_ms = (time.perf_counter() - t_analyze) * 1000

    pipeline = [
        {"id":"ingest","label":"Ingest","detail":f"{size_kb} KB · SHA-256 `{fhash[:12]}…`","status":"ok","ms":round(ingest_ms,3)},
        {"id":"parse","label":"Parse & types","detail":f"{len(df)} rows × {len(df.columns)} cols","status":"ok","ms":round(parse_ms,3)},
        {"id":"profile_rules","label":"Profile + rules","detail":"Nulls · outliers · mixed types · correlations · dup rows","status":"ok","ms":round(analyze_ms,3)},
        {"id":"report","label":"Assemble report","detail":"Health score · severity · JSON payload","status":"ok","ms":0.02},
    ]
    report.update({"filename": name, "fingerprint": fhash[:16], "cached": False,
                   "pipeline": pipeline, "pipeline_total_ms": round(sum(s["ms"] for s in pipeline), 3)})
    cache[fhash] = report
    return report


@app.get("/api/sample/messy-crm.csv")
async def sample_messy_crm():
    csv = """user_id,email,signup_date,revenue_usd,segment,last_login
1,alice@example.com,2024-01-15,120.5,paid,2024-06-01
2,,2024-02-20,0,freemium,
3,bob@invalid,not-a-date,99.9,paid,2024-05-10
1,alice@example.com,2024-01-15,120.5,paid,2024-06-01
4,carol@x.com,2024-03-01,5000000,outlier,2024-06-02
5,dave@x.com,2024-04-10,,freemium,2024-06-03
6,42,2024-05-05,10,freemium,2024-06-04
7,eve@x.com,2024-05-06,20,paid,2024-06-05
8,,,,,
9,frank@x.com,2024-07-01,50,paid,2024-08-01
"""
    return Response(content=csv, media_type="text/csv",
                    headers={"Content-Disposition": 'inline; filename="messy-crm-sample.csv"'})


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()

app.mount("/static", StaticFiles(directory="static"), name="static")
