import os
import io
import time
import logging
from typing import List, Optional, Dict, Any

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Response, Body, Header
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


def _log_request(name: str, rows: int, t0: float) -> None:
    try:
        ms = int((time.time() - t0) * 1000)
        log.info("%s rows=%s elapsed_ms=%s", name, rows, ms)
    except Exception:
        pass


_DATA_CACHE: Dict[str, Dict[str, Any]] = {"flights": {}, "daily": {}}


def _read_csv_cached(path: str, key: str) -> pd.DataFrame:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        raise HTTPException(status_code=500, detail=f"File not found: {path}")
    cache = _DATA_CACHE.get(key, {})
    if cache.get("mtime") == mtime and isinstance(cache.get("df"), pd.DataFrame):
        return cache["df"].copy()
    df = pd.read_csv(path)
    cache.update({"mtime": mtime, "df": df})
    _DATA_CACHE[key] = cache
    return df.copy()


def load_flights() -> pd.DataFrame:
    p = config.FILE_FLIGHTS
    if not os.path.exists(p):
        raise HTTPException(status_code=500, detail=f"Flights file not found: {p}")
    df = _read_csv_cached(p, "flights")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    return df


def load_daily() -> pd.DataFrame:
    p = config.FILE_DAILY
    if not os.path.exists(p):
        raise HTTPException(status_code=500, detail=f"Daily file not found: {p}")
    df = _read_csv_cached(p, "daily")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    return df


def _apply_filters(
    flights: pd.DataFrame,
    date_from: Optional[str],
    date_to: Optional[str],
    region: Optional[str],
    zone: Optional[str],
    altitude_category: Optional[str],
) -> pd.DataFrame:
    df = flights
    # Robust scalar date parsing: ignore if invalid / out-of-bounds
    if date_from:
        dt_from = pd.to_datetime(date_from, errors="coerce")
        if pd.notna(dt_from):
            df = df[pd.to_datetime(df["date"], errors="coerce") >= dt_from]
    if date_to:
        dt_to = pd.to_datetime(date_to, errors="coerce")
        if pd.notna(dt_to):
            df = df[pd.to_datetime(df["date"], errors="coerce") <= dt_to]
    if region and region.upper() not in ("ALL", "*", "ВСЕ"):
        df = df[df["region"] == region]
    if zone:
        zcol = "zone_clean" if "zone_clean" in df.columns else "zone"
        df = df[df[zcol].astype(str).str.upper() == zone.upper()]
    if altitude_category and "altitude_category" in df.columns:
        df = df[df["altitude_category"].astype(str).str.upper() == altitude_category.upper()]
    return df


def _pct_delta(curr: float, prev: float) -> float | None:
    try:
        if prev == 0:
            return None
        return round((curr - prev) / prev * 100.0, 1)
    except Exception:
        return None


def _call_llm(prompt: str, system: str = "Ты — аналитик данных. Пиши кратко на русском.") -> dict | None:
    base = config.AI_API_BASE
    key = config.AI_API_KEY
    model = config.AI_MODEL
    if not base or not key or not model:
        return None
    try:
        import requests
        url = base.rstrip("/") + "/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=config.AI_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        # OpenAI-compatible response
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        usage = data.get("usage", {})
        return {"text": text, "usage": usage, "model": model}
    except Exception as e:
        log.warning("LLM call failed: %s", e)
        return None


@app.post("/ai/analyze")
def ai_analyze(
    payload: Dict[str, Any] = Body(default={}),
    Authorization: Optional[str] = Header(default=None),
):
    _require_auth(Authorization)
    t0 = time.time()
    f = payload or {}
    date_from = f.get("date_from")
    date_to = f.get("date_to")
    region = f.get("region")
    zone = f.get("zone")
    altitude_category = f.get("altitude_category")

    flights = _apply_filters(load_flights(), date_from, date_to, region, zone, altitude_category)
    daily = recompute_daily_aggregates(flights)
    flights_valid = flights[~flights["date"].isna() & ~flights["region"].isna()].copy()

    flights_total = int(len(flights_valid))
    regions_count = int(flights_valid["region"].nunique())
    top_regions = (
        flights_valid.groupby("region")["reg_num"].count().sort_values(ascending=False).head(10).reset_index()
        .rename(columns={"reg_num": "flights_cnt"})
        .to_dict(orient="records")
    )
    # Aggregate daily sum for last 60 days
    agg = pd.DataFrame(columns=["date", "flights_cnt"])
    if not daily.empty:
        agg = daily.groupby("date")["flights_cnt"].sum().reset_index().sort_values("date").tail(60)
    last_line = "Нет данных"
    if not agg.empty:
        last_line = f"Последний день: {agg['date'].iloc[-1]} — {int(agg['flights_cnt'].iloc[-1])} полётов."

    # Compose prompt context
    lines = [
        "Сводка по полётам:",
        f"Период: {date_from or '-'}..{date_to or '-'}; Регион: {region or 'все'}; Зона: {zone or '—'}; Высота: {altitude_category or '—'}.",
        f"Итого полётов: {flights_total}; регионов: {regions_count}.",
        "Топ-5 регионов:" + ", ".join([f"{r['region']}: {int(r['flights_cnt'])}" for r in top_regions[:5]]) if top_regions else "Топ-5 регионов: —",
        last_line,
    ]
    # add compact timeseries line
    if not agg.empty:
        sample = ", ".join([f"{str(d)[:10]}:{int(v)}" for d, v in zip(agg["date"].astype(str).tolist()[-7:], agg["flights_cnt"].tolist()[-7:])])
        lines.append("Последние 7 дней: " + sample)

    prompt = "\n".join(lines) + "\n\nДай короткий аналитический отчёт: тренды, пики, гипотезы причин, рекомендации."

    llm = _call_llm(prompt)
    if llm and llm.get("text"):
        text = llm["text"]
        model = llm.get("model")
        usage = llm.get("usage")
        _log_request("ai_analyze_llm", flights_total, t0)
        return {"analysis": text, "used_model": model, "usage": usage}

    # fallback rule-based summary
    parts = [
        lines[0], lines[1], lines[2], lines[3], lines[4],
        "Рекомендации: мониторить аномальные пики; уточнить источники по топ-регионам; уточнить качество координат.",
    ]
    text = "\n".join([p for p in parts if p])
    _log_request("ai_analyze_fallback", flights_total, t0)
    return {"analysis": text, "used_model": None}


@app.get("/health")
def health():
    return {"status": "ok", "version": config.VERSION}


@app.get("/ai/health")
def ai_health():
    return {
        "enabled": bool(config.AI_API_KEY and (config.AI_API_BASE or True)),
        "base": config.AI_API_BASE or "(default: https://api.deepseek.com)",
        "model": config.AI_MODEL,
        "has_key": bool(config.AI_API_KEY),
    }


@app.get("/metrics/daily")
def metrics_daily(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    altitude_category: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(default=None),
):
    _require_auth(Authorization)
    t0 = time.time()
    flights = load_flights()
    flights = _apply_filters(flights, date_from, date_to, region, zone, altitude_category)

    daily = recompute_daily_aggregates(flights)
    daily = daily.sort_values(["region", "date"]).reset_index(drop=True)
    # Convert date to ISO
    daily["date"] = pd.to_datetime(daily["date"]).dt.date.astype(str)
    # Replace NaN with None for JSON
    records = daily.to_dict(orient="records")
    records = _sanitize_for_json(records)
    _log_request("metrics_daily", len(records), t0)
    return records


@app.get("/metrics/summary")
def metrics_summary(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    altitude_category: Optional[str] = Query(None),
    top_n: int = 5,
    Authorization: Optional[str] = Header(default=None),
):
    _require_auth(Authorization)
    t0 = time.time()
    flights = load_flights()
    flights = _apply_filters(flights, date_from, date_to, region, zone, altitude_category)

    flights_valid = flights[~flights["date"].isna() & ~flights["region"].isna()].copy()
    flights_total = int(len(flights_valid))
    regions_count = int(flights_valid["region"].nunique())
    top_regions = (
        flights_valid.groupby("region")["reg_num"].count().sort_values(ascending=False).head(top_n).reset_index()
    )
    zcol = "zone_clean" if "zone_clean" in flights_valid.columns else "zone"
    vc = flights_valid[zcol].dropna().astype(str).str.upper().value_counts().head(10)
    top_zones = [{"zone": str(idx), "flights_cnt": int(cnt)} for idx, cnt in vc.items()]
    resp = {
        "flights_total": flights_total,
        "regions_count": regions_count,
        "top_regions": top_regions.rename(columns={"reg_num": "flights_cnt"}).to_dict(orient="records"),
        "top_zones": top_zones,
    }
    _log_request("metrics_summary", flights_total, t0)
    return resp


@app.get("/flights")
def flights_endpoint(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    altitude_category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    Authorization: Optional[str] = Header(default=None),
):
    _require_auth(Authorization)
    t0 = time.time()
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
    if altitude_category:
        if "altitude_category" in flights.columns:
            flights = flights[flights["altitude_category"].astype(str).str.upper() == altitude_category.upper()]

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
    _log_request("flights", total, t0)
    return {"total": total, "items": records}


@app.get("/forecast")
def forecast_endpoint(
    region: str = Query(...),
    horizon: int = Query(14, ge=1, le=60),
    Authorization: Optional[str] = Header(default=None),
):
    _require_auth(Authorization)
    t0 = time.time()
    daily = load_daily()
    # Aggregate mode: region == ALL / * / ВСЕ -> aggregate across all regions
    region_req = (region or "").strip()
    if region_req.upper() in ("ALL", "__ALL__", "*", "ВСЕ"):
        agg = (
            daily.groupby("date", dropna=False)["flights_cnt"].sum().reset_index()
        )
        agg["region"] = "ALL"
        sub = agg[["region", "date", "flights_cnt"]]
        fc = forecast_by_region(sub, horizon_days=horizon)
        fc = fc[fc["region"] == "ALL"].copy()
    else:
        sub = daily[daily["region"] == region_req]
        if sub.empty:
            return {"region": region_req, "items": []}
        fc = forecast_by_region(sub.rename(columns={"flights_cnt": "flights_cnt"}), horizon_days=horizon)
        fc = fc[fc["region"] == region_req].copy()
    fc["date"] = pd.to_datetime(fc["date"]).dt.date.astype(str)
    items = fc[["date", "yhat", "method"]].to_dict(orient="records")
    _log_request("forecast", len(items), t0)
    return {"region": region_req, "items": items}


@app.get("/metrics/overview")
def metrics_overview(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    altitude_category: Optional[str] = Query(None),
    top_n: int = 10,
    Authorization: Optional[str] = None,
):
    _require_auth(Authorization)
    t0 = time.time()
    flights = _apply_filters(load_flights(), date_from, date_to, region, zone, altitude_category)
    valid = flights[~flights["date"].isna() & ~flights["region"].isna()].copy()
    flights_total = int(len(valid))
    regions_count = int(valid["region"].nunique())
    # top regions
    top_regions = (
        valid.groupby("region")["reg_num"].count().sort_values(ascending=False).head(top_n).reset_index()
    ).rename(columns={"reg_num": "flights_cnt"})
    # zone distribution
    zcol = "zone_clean" if "zone_clean" in valid.columns else "zone"
    top_zones = (
        valid[zcol].dropna().astype(str).str.upper().value_counts().head(top_n).rename_axis("zone").reset_index(name="flights_cnt")
    )
    # altitude distribution
    if "altitude_category" in valid.columns:
        alt_dist = (
            valid["altitude_category"].dropna().astype(str).str.upper().value_counts().rename_axis("altitude_category").reset_index(name="flights_cnt")
        )
    else:
        alt_dist = pd.DataFrame(columns=["altitude_category", "flights_cnt"])

    # day-over-day and week-over-week deltas on aggregate
    daily = recompute_daily_aggregates(valid)
    if daily.empty:
        dod_pct = None
        wow_pct = None
    else:
        agg = daily.groupby("date")["flights_cnt"].sum().reset_index().sort_values("date")
        # DoD
        last = agg["flights_cnt"].iloc[-1]
        prev = agg["flights_cnt"].iloc[-2] if len(agg) >= 2 else 0
        dod_pct = _pct_delta(float(last), float(prev)) if len(agg) >= 2 else None
        # WoW (last 7 vs previous 7)
        last7 = float(agg["flights_cnt"].tail(7).sum())
        prev7 = float(agg["flights_cnt"].iloc[max(0, len(agg)-14):max(0, len(agg)-7)].sum()) if len(agg) >= 14 else 0.0
        wow_pct = _pct_delta(last7, prev7) if len(agg) >= 14 else None

    resp = {
        "flights_total": flights_total,
        "regions_count": regions_count,
        "top_regions": top_regions.to_dict(orient="records"),
        "top_zones": top_zones.to_dict(orient="records"),
        "altitude_distribution": alt_dist.to_dict(orient="records"),
        "deltas": {"dod_pct": dod_pct, "wow_pct": wow_pct},
    }
    _log_request("metrics_overview", flights_total, t0)
    return resp


@app.get("/metrics/timeseries")
def metrics_timeseries(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    altitude_category: Optional[str] = Query(None),
    include_forecast: bool = Query(True),
    horizon: int = Query(14, ge=1, le=60),
    Authorization: Optional[str] = None,
):
    _require_auth(Authorization)
    t0 = time.time()
    flights = _apply_filters(load_flights(), date_from, date_to, region, zone, altitude_category)
    daily = recompute_daily_aggregates(flights)
    if daily.empty:
        return {"items": [], "forecast": []}
    # aggregate across regions (sum per date)
    agg = daily.groupby("date")["flights_cnt"].sum().reset_index().sort_values("date")
    agg["ma7"] = agg["flights_cnt"].rolling(window=7, min_periods=1).mean().round(1)
    agg["sum7"] = agg["flights_cnt"].rolling(window=7, min_periods=1).sum().round(0)
    items = agg.assign(date=pd.to_datetime(agg["date"]).dt.date.astype(str)).to_dict(orient="records")

    fc_items: list[dict] = []
    if include_forecast:
        # Build daily across all regions to feed forecast_by_region
        ts = agg.copy()
        ts["region"] = "ALL"
        ts = ts.rename(columns={"flights_cnt": "flights_cnt"})
        fc = forecast_by_region(ts[["region", "date", "flights_cnt"]], horizon_days=horizon)
        fc["date"] = pd.to_datetime(fc["date"]).dt.date.astype(str)
        fc_items = fc[["date", "yhat", "method"]].to_dict(orient="records")

    resp = {"items": items, "forecast": fc_items}
    _log_request("metrics_timeseries", len(items), t0)
    return resp


@app.get("/export.csv")
def export_csv(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    Authorization: Optional[str] = Header(default=None),
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
    Authorization: Optional[str] = Header(default=None),
):
    _require_auth(Authorization)
    # Simple PDF summary via reportlab
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors
    except Exception as e:
        raise HTTPException(status_code=500, detail="PDF export unavailable (reportlab not installed)")

    flights = _apply_filters(load_flights(), date_from, date_to, region, None, None)

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

    # Simple line chart for last 30 days (flights_cnt sum)
    try:
        d30 = daily.sort_values("date").tail(30)
        if not d30.empty:
            y -= 10
            c.setFont("Helvetica-Bold", 12)
            c.drawString(40, y, "Last 30 days (sum by day)")
            y -= 6
            # chart area
            x0, x1 = 60, width - 40
            y0, y1 = y - 120, y - 10
            c.setStrokeColor(colors.grey)
            c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
            # scale
            dsum = d30.groupby("date")["flights_cnt"].sum().reset_index()
            xs = list(range(len(dsum)))
            ymin, ymax = 0, max(1, int(dsum["flights_cnt"].max() * 1.1))
            def sx(i):
                return x0 + (i / max(1, len(xs)-1)) * (x1 - x0)
            def sy(v):
                return y0 + (v - ymin) / (ymax - ymin) * (y1 - y0)
            # plot line
            c.setStrokeColor(colors.lightblue)
            c.setLineWidth(1.5)
            last_x = last_y = None
            for i, v in enumerate(dsum["flights_cnt"].tolist()):
                px, py = sx(i), sy(v)
                if last_x is not None:
                    c.line(last_x, last_y, px, py)
                last_x, last_y = px, py
            y = y0 - 10
    except Exception:
        pass

    c.showPage()
    c.save()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=report.pdf"})
