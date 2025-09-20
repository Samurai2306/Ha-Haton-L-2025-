from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from .geo import try_parse_coord


log = logging.getLogger(__name__)


@dataclass
class QARecord:
    issue_type: str
    row_index: int
    description: str


ALT_LOW_THRESHOLD = 100  # M0100 and below -> LOW
ALT_MID_THRESHOLD = 300  # M0101..M0300 -> MID; above -> HIGH


def _extract_m_values(altitude_raw: str | None) -> List[int]:
    if not altitude_raw or not isinstance(altitude_raw, str):
        return []
    # Find sequences like Mdddd
    vals = []
    for m in re.findall(r"M(\d{4})", altitude_raw):
        try:
            vals.append(int(m))
        except Exception:
            pass
    return vals


def altitude_category(altitude_raw: str | None) -> str | None:
    vals = _extract_m_values(altitude_raw)
    if not vals:
        return None
    v = max(vals)  # use the max seen
    if v <= ALT_LOW_THRESHOLD:
        return "LOW"
    if v <= ALT_MID_THRESHOLD:
        return "MID"
    return "HIGH"


def clean_zone(z: str | None) -> str | None:
    if z is None:
        return None
    s = str(z).strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s or None


def parse_point_to_coords(token: str | None) -> Tuple[float | None, float | None]:
    # Treat NaN and None as missing
    if token is None or (isinstance(token, float) and np.isnan(token)):
        return (None, None)
    s = str(token).strip()
    if not s:
        return (None, None)
    lat, lon = try_parse_coord(s)
    return (lat, lon)


def run_qc_and_enrich(flights_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    - Validate dates/regions
    - Fix invalid duration_min (<0 or >1440) -> set NaN
    - Remove duplicates by (date, region, reg_num, dep_time_utc, arr_time_utc) keeping the row with more non-null fields
    - Add altitude_category, zone_clean, dep_lat/lon, arr_lat/lon
    Returns: (enriched_flights_df, qa_issues_df)
    """
    df = flights_df.copy()

    # Normalize columns expected
    required_cols = [
        "date",
        "region",
        "dep_time_utc",
        "arr_time_utc",
        "duration_min",
        "reg_num",
        "zone",
        "altitude_raw",
        "dep_point",
        "arr_point",
    ]
    for c in required_cols:
        if c not in df.columns:
            df[c] = np.nan

    issues: list[QARecord] = []

    # Date format to datetime.date
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    # Region clean
    df["region"] = df["region"].astype(str).str.strip()
    df.loc[df["region"].isin(["", "None", "nan"]), "region"] = np.nan

    # Duration checks
    def _check_duration(x) -> float | np.nan:
        try:
            if pd.isna(x):
                return np.nan
            v = float(x)
            if v < 0 or v > 1440:
                return np.nan
            return v
        except Exception:
            return np.nan

    invalid_duration_mask = (~df["duration_min"].isna()) & (
        (pd.to_numeric(df["duration_min"], errors="coerce") < 0)
        | (pd.to_numeric(df["duration_min"], errors="coerce") > 1440)
    )
    for idx in df.index[invalid_duration_mask]:
        issues.append(QARecord("invalid_duration", int(idx), "duration_min out of range; set to NaN"))
    df["duration_min"] = df["duration_min"].map(_check_duration)

    # Enrichment
    df["altitude_category"] = df["altitude_raw"].map(altitude_category)
    df["zone_clean"] = df["zone"].map(clean_zone)

    dep_coords = df["dep_point"].map(parse_point_to_coords)
    df["dep_lat"] = dep_coords.map(lambda t: t[0])
    df["dep_lon"] = dep_coords.map(lambda t: t[1])
    arr_coords = df["arr_point"].map(parse_point_to_coords)
    df["arr_lat"] = arr_coords.map(lambda t: t[0])
    df["arr_lon"] = arr_coords.map(lambda t: t[1])

    # Duplicates: key
    key_cols = ["date", "region", "reg_num", "dep_time_utc", "arr_time_utc"]
    df["_nonnull_count"] = df.notna().sum(axis=1)
    # Sort so that the record with more non-null fields comes first
    df = df.sort_values(by=key_cols + ["_nonnull_count"], ascending=[True, True, True, True, True, False])
    dup_mask = df.duplicated(subset=key_cols, keep="first")
    for idx in df.index[dup_mask]:
        issues.append(QARecord("duplicate", int(idx), "duplicate key; dropped"))
    df = df[~dup_mask].copy()
    df.drop(columns=["_nonnull_count"], inplace=True)

    # Empty date/region — mark issue and drop from aggregates; keep in file but flagged
    empty_mask = df["date"].isna() | df["region"].isna()
    for idx in df.index[empty_mask]:
        issues.append(QARecord("missing_date_or_region", int(idx), "record lacks date or region"))

    qa_df = pd.DataFrame([r.__dict__ for r in issues]) if issues else pd.DataFrame(columns=["issue_type", "row_index", "description"])
    return df, qa_df


def recompute_daily_aggregates(flights_df: pd.DataFrame) -> pd.DataFrame:
    # Exclude rows without date or region
    df = flights_df[~flights_df["date"].isna() & ~flights_df["region"].isna()].copy()

    agg = (
        df.groupby(["region", "date"], dropna=False)
        .agg(
            flights_cnt=("reg_num", "count"),
            avg_duration_min=("duration_min", "mean"),
            p50_duration_min=("duration_min", lambda x: np.nanpercentile([v for v in x if pd.notna(v)], 50) if any(pd.notna(x)) else np.nan),
            p90_duration_min=("duration_min", lambda x: np.nanpercentile([v for v in x if pd.notna(v)], 90) if any(pd.notna(x)) else np.nan),
        )
        .reset_index()
    )
    for col in ["avg_duration_min", "p50_duration_min", "p90_duration_min"]:
        agg[col] = pd.to_numeric(agg[col], errors="coerce").round(1)
    return agg
