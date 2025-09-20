#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL post-processing from existing CSVs.
- Loads flights_normalized.csv
- Runs QA checks, enrichment (altitude_category, zone_clean, coords)
- Recomputes daily_aggregates.csv
- Writes qa_issues.csv
"""
import sys
import logging
import pandas as pd

from uav_analytics import config
from uav_analytics.logging_utils import setup_logging
from uav_analytics.etl import run_qc_and_enrich, recompute_daily_aggregates


def main():
    setup_logging()
    log = logging.getLogger("etl")
    log.info("Loading flights: %s", config.FILE_FLIGHTS)
    flights = pd.read_csv(config.FILE_FLIGHTS)

    enriched, qa = run_qc_and_enrich(flights)
    log.info("QA issues: %d", len(qa))

    # Save enriched flights back to the same file
    enriched.to_csv(config.FILE_FLIGHTS, index=False, encoding="utf-8-sig")
    qa.to_csv(config.FILE_QA, index=False, encoding="utf-8-sig")
    log.info("Saved: %s, %s", config.FILE_FLIGHTS, config.FILE_QA)

    daily = recompute_daily_aggregates(enriched)
    daily.to_csv(config.FILE_DAILY, index=False, encoding="utf-8-sig")
    log.info("Saved: %s", config.FILE_DAILY)


if __name__ == "__main__":
    sys.exit(main())

