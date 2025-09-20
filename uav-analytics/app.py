#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UAV Analytics Pipeline (БПЛА) — парсинг SHR/DEP/ARR + агрегаты + простой прогноз

Вход:  2024.xlsx, 2025.xlsx
Выход: flights_normalized.csv, daily_aggregates.csv, forecast_14d.csv

Зависимости: pandas, numpy, openpyxl
(Опционально) statsmodels для Holt-Winters. Если отсутствует — будет fallback.
"""
import re
import os
import sys
import math
import json
import warnings
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# ---- Опционально пытаемся подключить Holt-Winters ----
HW_AVAILABLE = True
try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except Exception:
    HW_AVAILABLE = False
    warnings.warn("statsmodels не найден. Прогноз будет на наивной скользящей средней.")

# =========================
# Константы/пути
# =========================
FILE_2024 = "2024.xlsx"
FILE_2025 = "2025.xlsx"

OUT_FLIGHTS = "flights_normalized.csv"
OUT_DAILY = "daily_aggregates.csv"
OUT_FORECAST = "forecast_14d.csv"

# =========================
# Вспомогательные функции парсинга
# =========================

def _clean_text(x):
    if pd.isna(x):
        return ""
    return str(x).replace("\r", "\n").strip()

def _re_search(pattern, text, flags=re.IGNORECASE):
    if not text:
        return None
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None

def parse_time_from_block(block_text):
    """
    Ищем время формата -ZZZZHHMM (из SHR/DEP/ARR). Берём первое вхождение.
    Возвращаем строку HH:MM (UTC), либо None.
    """
    t = _re_search(r"-ZZZZ(\d{4})", block_text)
    if t:
        return f"{t[:2]}:{t[2:]}"
    return None

def parse_dof(block_text):
    """
    Ищем дату полёта DOF/YYMMDD. Возвращаем date().
    """
    d = _re_search(r"DOF/(\d{6})", block_text)
    if d:
        # YYMMDD -> 20YY-MM-DD (гипотеза: 20xx)
        yy = int(d[:2])
        mm = int(d[2:4])
        dd = int(d[4:6])
        year = 2000 + yy
        try:
            return datetime(year, mm, dd).date()
        except ValueError:
            return None
    return None

def parse_reg(block_text):
    """
    REG/<алфанум>. Пример: REG/07C4935
    """
    return _re_search(r"REG/([A-Z0-9]+)", block_text)

def parse_zone(block_text):
    """
    Ищем описания зоны вида 'ZONA ...' до конца строки/сегмента.
    Берём после 'ZONA' всё до конца строки/скобки/перевода строки.
    """
    z = _re_search(r"ZONA\s+([^\n\-\)]+)", block_text)
    if z:
        return z.strip()
    return None

def parse_altitude(block_text):
    """
    Пытаемся вытащить высотные указания.
    Часто встречаются фрагменты вида 'K0300M3000' или '-M0000/M0080'.
    Будем возвращать сырец (как строку), чтобы не потерять информацию.
    """
    # Ищем KddddMdddd или -Mdddd(/Mdddd)
    k_m = _re_search(r"(K\d{4}M\d{4})", block_text)
    if k_m:
        return k_m
    m_only = _re_search(r"-(M\d{4}(?:/M\d{4})?)", block_text)
    if m_only:
        return m_only
    return None

def parse_point(after_key):
    """
    Универсальный парсер точки после префикса DEP/ или ARR/
    Возвращаем короткую строку до пробела/перевода строки/закрывающей скобки.
    """
    if not after_key:
        return None
    # Иногда указывается координатная пара или код точки. Возьмём «до разделителя».
    return re.split(r"[\s\)\n]", after_key)[0].strip() if after_key else None

def parse_dep_point(block_text):
    return parse_point(_re_search(r"DEP/([^\s\)\n]+)", block_text))

def parse_arr_point(block_text):
    return parse_point(_re_search(r"ARR/([^\s\)\n]+)", block_text))

def first_nonempty(*vals):
    for v in vals:
        if v not in (None, "", np.nan):
            return v
    return None

def infer_duration(dep_time_str, arr_time_str, date_dof=None):
    """
    Подсчёт длительности полёта в минутах, если есть время DEP и ARR (HH:MM).
    Допущение: время UTC, перелёт максимум сутки. Если ARR < DEP — считаем, что прибытие на следующий день.
    """
    if not dep_time_str or not arr_time_str:
        return None
    try:
        fmt = "%H:%M"
        dep_dt = datetime.strptime(dep_time_str, fmt)
        arr_dt = datetime.strptime(arr_time_str, fmt)
        if arr_dt < dep_dt:
            arr_dt += timedelta(days=1)
        return int((arr_dt - dep_dt).total_seconds() // 60)
    except Exception:
        return None

# =========================
# Нормализация строк в полёт
# =========================

def normalize_rows(df, source_year=None):
    """
    Преобразуем строки таблиц 2024.xlsx и 2025.xlsx в единую нормальную структуру.
    Ожидаемые колонки:
      - 2025: 'Центр ЕС ОрВД', 'SHR', 'DEP', 'ARR'
      - 2024: может быть 'Дата полёта', 'Сообщение SHR', 'Сообщение DEP', 'Сообщение ARR'
    """
    # Мягкое сопоставление названий колонок
    col_map = {}
    for c in df.columns:
        cn = str(c).strip().lower()
        if "центр" in cn and "орвд" not in cn:
            # на всякий случай
            pass
        if "центр" in cn:
            col_map["region"] = c
        elif cn in ("shr", "сообщение shr"):
            col_map["shr"] = c
        elif cn in ("dep", "сообщение dep", "сообщение dep "):
            col_map["dep"] = c
        elif cn in ("arr", "сообщение arr", "сообщение arr "):
            col_map["arr"] = c
        elif "дата" in cn:
            col_map["date_col"] = c

    region_col = col_map.get("region")
    shr_col = col_map.get("shr")
    dep_col = col_map.get("dep")
    arr_col = col_map.get("arr")
    date_col = col_map.get("date_col")

    out = []
    for i, row in df.iterrows():
        region = _clean_text(row.get(region_col)) if region_col in df.columns else None
        shr = _clean_text(row.get(shr_col)) if shr_col in df.columns else ""
        dep = _clean_text(row.get(dep_col)) if dep_col in df.columns else ""
        arr = _clean_text(row.get(arr_col)) if arr_col in df.columns else ""

        # Время: приоритет DEP/ARR, fallback на SHR
        dep_time = first_nonempty(parse_time_from_block(dep), parse_time_from_block(shr))
        arr_time = first_nonempty(parse_time_from_block(arr), parse_time_from_block(shr))

        # DOF и дата:
        dof_dep = parse_dof(dep)
        dof_arr = parse_dof(arr)
        dof_shr = parse_dof(shr)
        dof = first_nonempty(dof_dep, dof_arr, dof_shr)

        # Если есть явная "Дата полёта" колонка — используем её
        if date_col in df.columns and not pd.isna(row.get(date_col)):
            try:
                d = pd.to_datetime(row.get(date_col)).date()
                dof = d
            except Exception:
                pass

        reg_num = first_nonempty(parse_reg(dep), parse_reg(arr), parse_reg(shr))
        zone = first_nonempty(parse_zone(shr), parse_zone(dep), parse_zone(arr))
        altitude = first_nonempty(parse_altitude(shr), parse_altitude(dep), parse_altitude(arr))
        dep_point = first_nonempty(parse_dep_point(dep), parse_dep_point(shr))
        arr_point = first_nonempty(parse_arr_point(arr), parse_arr_point(shr))

        duration_min = infer_duration(dep_time, arr_time, dof)

        out.append({
            "source_year": source_year,
            "region": region,
            "date": dof,                    # date
            "dep_time_utc": dep_time,       # HH:MM
            "arr_time_utc": arr_time,       # HH:MM
            "duration_min": duration_min,   # int or None
            "reg_num": reg_num,
            "zone": zone,
            "altitude_raw": altitude,
            "dep_point": dep_point,
            "arr_point": arr_point,
            "shr_raw": shr,
            "dep_raw": dep,
            "arr_raw": arr,
        })

    return pd.DataFrame(out)

# =========================
# Прогноз по регионам (14 дней)
# =========================

def forecast_by_region(daily_df, horizon_days=14):
    """
    Ожидает daily_df с колонками: date (datetime.date), region, flights_cnt (int)
    Возвращает объединённый прогноз на horizon_days по каждому региону.
    """
    if daily_df.empty:
        return pd.DataFrame(columns=["region", "date", "yhat", "method"])

    daily_df = daily_df.copy()
    daily_df["date"] = pd.to_datetime(daily_df["date"])

    all_regs = sorted([r for r in daily_df["region"].dropna().unique()])
    forecasts = []

    for reg in all_regs:
        sub = daily_df[daily_df["region"] == reg].sort_values("date")
        # Минимальная длина для модели
        if len(sub) < 7:
            # слишком мало — наивная медиана
            base = int(sub["flights_cnt"].median()) if len(sub) else 0
            last_date = sub["date"].max() if len(sub) else pd.Timestamp.today().normalize()
            for d in range(1, horizon_days + 1):
                forecasts.append({"region": reg,
                                  "date": (last_date + pd.Timedelta(days=d)).date(),
                                  "yhat": base,
                                  "method": "naive-median"})
            continue

        y = sub["flights_cnt"].values.astype(float)
        idx = pd.DatetimeIndex(sub["date"])

        # По умолчанию — Holt-Winters с недельной сезонностью (7)
        if HW_AVAILABLE and len(sub) >= 14:
            try:
                # additive тренд/сезонность — для счётчиков это нормальный baseline
                model = ExponentialSmoothing(
                    y,
                    trend="add",
                    seasonal="add",
                    seasonal_periods=7
                ).fit(optimized=True)
                future_idx = pd.date_range(idx.max() + pd.Timedelta(days=1), periods=horizon_days, freq="D")
                yhat = model.forecast(horizon_days)
                for d, val in zip(future_idx, yhat):
                    forecasts.append({"region": reg, "date": d.date(), "yhat": max(0, float(val)), "method": "holt-winters"})
                continue
            except Exception as e:
                warnings.warn(f"[{reg}] Holt-Winters не удался: {e}")

        # Fallback: простая скользящая средняя по последним 7 дням
        window = min(7, len(sub))
        base = float(pd.Series(y).tail(window).mean())
        last_date = sub["date"].max()
        for d in range(1, horizon_days + 1):
            forecasts.append({"region": reg,
                              "date": (last_date + pd.Timedelta(days=d)).date(),
                              "yhat": max(0, base),
                              "method": "moving-average"})

    return pd.DataFrame(forecasts)

# =========================
# Главный сценарий
# =========================

def main():
    # 1) Чтение двух книг (первый лист по умолчанию)
    if not os.path.exists(FILE_2024):
        print(f"Не найден {FILE_2024}", file=sys.stderr)
    if not os.path.exists(FILE_2025):
        print(f"Не найден {FILE_2025}", file=sys.stderr)

    df24 = pd.read_excel(FILE_2024, sheet_name=0)
    df25 = pd.read_excel(FILE_2025, sheet_name=0)

    # 2) Нормализация
    norm24 = normalize_rows(df24, source_year=2024)
    norm25 = normalize_rows(df25, source_year=2025)

    flights = pd.concat([norm24, norm25], ignore_index=True)

    # 3) Приводим дату к datetime.date
    flights["date"] = pd.to_datetime(flights["date"], errors="coerce").dt.date

    # 4) Базовые чистки
    # убираем строки без даты вообще — для суточной аналитики они бесполезны
    flights = flights[~flights["date"].isna()].copy()

    # 5) Сохраняем нормализованные полёты
    flights.to_csv(OUT_FLIGHTS, index=False, encoding="utf-8-sig")

    # 6) Агрегаты по дням и регионам
    #    flights_cnt, avg_duration_min, p50, p90
    agg = (flights
           .groupby(["region", "date"], dropna=False)
           .agg(flights_cnt=("reg_num", "count"),
                avg_duration_min=("duration_min", "mean"),
                p50_duration_min=("duration_min", lambda x: np.nanpercentile([v for v in x if pd.notna(v)], 50) if any(pd.notna(x)) else np.nan),
                p90_duration_min=("duration_min", lambda x: np.nanpercentile([v for v in x if pd.notna(v)], 90) if any(pd.notna(x)) else np.nan))
           .reset_index())

    # Приводим длительности к числам, округлим до 1 знака
    for col in ["avg_duration_min", "p50_duration_min", "p90_duration_min"]:
        agg[col] = pd.to_numeric(agg[col], errors="coerce")
        agg[col] = agg[col].round(1)

    agg.to_csv(OUT_DAILY, index=False, encoding="utf-8-sig")

    # 7) Прогноз на 14 дней по каждому региону
    forecast = forecast_by_region(agg.rename(columns={"flights_cnt": "flights_cnt"}), horizon_days=14)
    forecast.to_csv(OUT_FORECAST, index=False, encoding="utf-8-sig")

    print(f"Готово.\n"
          f" • Нормализованные полёты: {OUT_FLIGHTS}\n"
          f" • Суточные агрегаты:       {OUT_DAILY}\n"
          f" • Прогноз (14 дней):       {OUT_FORECAST}")

if __name__ == "__main__":
    main()
