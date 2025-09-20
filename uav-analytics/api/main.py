import os
import io
import logging
from typing import List, Optional

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from uav_analytics import config
from uav_analytics.logging_utils import setup_logging
from uav_analytics.etl import recompute_daily_aggregates
from uav_analytics.forecast import forecast_by_region


setup_logging()
log = logging.getLogger("api")

app = FastAPI(title="UAV Analytics API", version=config.VERSION)

# CORS
if config.CORS_ORIGINS == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def auth_dependency(authorization: Optional[str] = Query(default=None, alias="Authorization", include_in_schema=False)):
    token = config.API_TOKEN
    if not token:
        return  # auth disabled
    # Accept header style too from request state
    # The FastAPI dependency with Query won't capture headers, so we read from environment in routes.
    return


def _require_auth(authorization_header: Optional[str]):
    token = config.API_TOKEN
    if not token:
        return  # no auth in dev
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    provided = authorization_header.split(" ", 1)[1].strip()
    if provided != token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _sanitize_for_json(data):
    import math
    if isinstance(data, float):
        if math.isnan(data) or data == float('inf') or data == float('-inf'):
            return None
        return data
    if isinstance(data, dict):
        return {k: _sanitize_for_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_sanitize_for_json(v) for v in data]
    return data


def load_flights() -> pd.DataFrame:
    p = config.FILE_FLIGHTS
    if not os.path.exists(p):
        raise HTTPException(status_code=500, detail=f"Flights file not found: {p}")
    df = pd.read_csv(p)
    # Normalize types
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    return df


def load_daily() -> pd.DataFrame:
    p = config.FILE_DAILY
    if not os.path.exists(p):
        raise HTTPException(status_code=500, detail=f"Daily file not found: {p}")
    df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    return df


@app.get("/health")
def health():
    return {"status": "ok", "version": config.VERSION}


@app.get("/metrics/daily")
def metrics_daily(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    Authorization: Optional[str] = None,
):
    _require_auth(Authorization)
    flights = load_flights()
    # Filters
    if date_from:
        flights = flights[pd.to_datetime(flights["date"], errors="coerce") >= pd.to_datetime(date_from)]
    if date_to:
        flights = flights[pd.to_datetime(flights["date"], errors="coerce") <= pd.to_datetime(date_to)]
    if region:
        flights = flights[flights["region"] == region]
    if zone:
        # prefer cleaned
        zcol = "zone_clean" if "zone_clean" in flights.columns else "zone"
        flights = flights[flights[zcol].astype(str).str.upper() == zone.upper()]

    daily = recompute_daily_aggregates(flights)
    daily = daily.sort_values(["region", "date"]).reset_index(drop=True)
    # Convert date to ISO
    daily["date"] = pd.to_datetime(daily["date"]).dt.date.astype(str)
    # Replace NaN with None for JSON
    records = daily.to_dict(orient="records")
    records = _sanitize_for_json(records)
    return records


@app.get("/metrics/summary")
def metrics_summary(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    top_n: int = 5,
    Authorization: Optional[str] = None,
):
    _require_auth(Authorization)
    flights = load_flights()
    if date_from:
        flights = flights[pd.to_datetime(flights["date"], errors="coerce") >= pd.to_datetime(date_from)]
    if date_to:
        flights = flights[pd.to_datetime(flights["date"], errors="coerce") <= pd.to_datetime(date_to)]
    if region:
        flights = flights[flights["region"] == region]
    if zone:
        zcol = "zone_clean" if "zone_clean" in flights.columns else "zone"
        flights = flights[flights[zcol].astype(str).str.upper() == zone.upper()]

    flights_valid = flights[~flights["date"].isna() & ~flights["region"].isna()].copy()
    flights_total = int(len(flights_valid))
    regions_count = int(flights_valid["region"].nunique())
    top_regions = (
        flights_valid.groupby("region")["reg_num"].count().sort_values(ascending=False).head(top_n).reset_index()
    )
    zcol = "zone_clean" if "zone_clean" in flights_valid.columns else "zone"
    vc = flights_valid[zcol].dropna().astype(str).str.upper().value_counts().head(10)
    top_zones = [{"zone": str(idx), "flights_cnt": int(cnt)} for idx, cnt in vc.items()]
    return {
        "flights_total": flights_total,
        "regions_count": regions_count,
        "top_regions": top_regions.rename(columns={"reg_num": "flights_cnt"}).to_dict(orient="records"),
        "top_zones": top_zones,
    }


@app.get("/flights")
def flights_endpoint(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    Authorization: Optional[str] = None,
):
    _require_auth(Authorization)
    flights = load_flights()
    if date_from:
        flights = flights[pd.to_datetime(flights["date"], errors="coerce") >= pd.to_datetime(date_from)]
    if date_to:
        flights = flights[pd.to_datetime(flights["date"], errors="coerce") <= pd.to_datetime(date_to)]
    if region:
        flights = flights[flights["region"] == region]

    cols = [
        "date",
        "region",
        "dep_time_utc",
        "arr_time_utc",
        "duration_min",
        "reg_num",
        "zone",
        "zone_clean" if "zone_clean" in flights.columns else "zone",
        "altitude_category" if "altitude_category" in flights.columns else "altitude_raw",
        "dep_point",
        "arr_point",
        "dep_lat" if "dep_lat" in flights.columns else None,
        "dep_lon" if "dep_lon" in flights.columns else None,
        "arr_lat" if "arr_lat" in flights.columns else None,
        "arr_lon" if "arr_lon" in flights.columns else None,
    ]
    cols = [c for c in cols if c]
    df = flights[cols].copy()
    df = df.sort_values(["date"]).reset_index(drop=True)
    total = len(df)
    df = df.iloc[offset : offset + limit]
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    records = df.to_dict(orient="records")
    records = _sanitize_for_json(records)
    return {"total": total, "items": records}


@app.get("/forecast")
def forecast_endpoint(
    region: str = Query(...),
    horizon: int = Query(14, ge=1, le=60),
    Authorization: Optional[str] = None,
):
    _require_auth(Authorization)
    daily = load_daily()
    sub = daily[daily["region"] == region]
    if sub.empty:
        return {"region": region, "items": []}
    fc = forecast_by_region(sub.rename(columns={"flights_cnt": "flights_cnt"}), horizon_days=horizon)
    fc = fc[fc["region"] == region].copy()
    fc["date"] = pd.to_datetime(fc["date"]).dt.date.astype(str)
    return {"region": region, "items": fc[["date", "yhat", "method"]].to_dict(orient="records")}


@app.get("/export.csv")
def export_csv(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    Authorization: Optional[str] = None,
):
    _require_auth(Authorization)
    flights = load_flights()
    if date_from:
        flights = flights[pd.to_datetime(flights["date"], errors="coerce") >= pd.to_datetime(date_from)]
    if date_to:
        flights = flights[pd.to_datetime(flights["date"], errors="coerce") <= pd.to_datetime(date_to)]
    if region:
        flights = flights[flights["region"] == region]

    out = io.StringIO()
    flights.to_csv(out, index=False)
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=flights_export.csv"})


@app.get("/export.pdf")
def export_pdf(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    Authorization: Optional[str] = None,
):
    _require_auth(Authorization)
    # Simple PDF summary via reportlab
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception as e:
        raise HTTPException(status_code=500, detail="PDF export unavailable (reportlab not installed)")

    flights = load_flights()
    if date_from:
        flights = flights[pd.to_datetime(flights["date"], errors="coerce") >= pd.to_datetime(date_from)]
    if date_to:
        flights = flights[pd.to_datetime(flights["date"], errors="coerce") <= pd.to_datetime(date_to)]
    if region:
        flights = flights[flights["region"] == region]

    daily = recompute_daily_aggregates(flights)
    # Build a simple summary
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "UAV Analytics — Summary Report")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Filters: date_from={date_from or '-'} date_to={date_to or '-'} region={region or '-'}")
    y -= 20
    flights_total = int(len(flights[~flights["date"].isna() & ~flights["region"].isna()]))
    regions_count = int(flights["region"].nunique())
    c.drawString(40, y, f"Flights total: {flights_total}   Regions: {regions_count}")
    y -= 30

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Top regions")
    y -= 18
    c.setFont("Helvetica", 10)
    top_regions = flights.groupby("region")["reg_num"].count().sort_values(ascending=False).head(5)
    for r, cnt in top_regions.items():
        c.drawString(48, y, f"{r}: {int(cnt)}")
        y -= 14

    c.showPage()
    c.save()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=report.pdf"})
