#!/usr/bin/env python3
"""
Compute the 30-day trailing average (up to 2025-09-26, inclusive)
of Base chain daily revenue (integer USD) using DefiLlama Fees API.
Print each day's revenue treated by its UTC calendar date, then
output the 30-day average rounded to the nearest integer USD.

Endpoint:
  https://api.llama.fi/summary/fees/base?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true&dataType=dailyRevenue
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta, date
from statistics import mean
from urllib.request import urlopen, Request


ENDPOINT = (
    "https://api.llama.fi/summary/fees/base"
    "?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true&dataType=dailyRevenue"
)
DATA_DIR = os.path.dirname(__file__)
RAW_PATH = os.path.join(DATA_DIR, "defillama_fees_base_daily_revenue_raw.json")

END_DATE = date(2025, 9, 26)  # inclusive
WINDOW_DAYS = 30
START_DATE = END_DATE - timedelta(days=WINDOW_DAYS - 1)


def fetch_and_save_raw() -> dict:
    req = Request(ENDPOINT, headers={"User-Agent": "metric-script/1.0"})
    with urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def load_raw_from_disk() -> dict | None:
    if not os.path.exists(RAW_PATH):
        return None
    with open(RAW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_utc_date(ts_val) -> date:
    # Accept seconds since epoch (int/float/str) or ISO 8601 string
    if isinstance(ts_val, (int, float)) or (isinstance(ts_val, str) and ts_val.isdigit()):
        ts_seconds = int(float(ts_val))
        return datetime.fromtimestamp(ts_seconds, tz=timezone.utc).date()
    if isinstance(ts_val, str):
        iso = ts_val.strip()
        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.date()
    raise ValueError(f"Unsupported timestamp: {ts_val!r}")


def main() -> None:
    try:
        payload = fetch_and_save_raw()
    except Exception as e:
        local = load_raw_from_disk()
        if local is None:
            raise RuntimeError(f"Failed to fetch data and no local raw file found: {e}")
        print(f"Warning: network fetch failed ({e}); using cached raw data at {RAW_PATH}")
        payload = local

    if not isinstance(payload, dict) or "totalDataChart" not in payload:
        raise ValueError("Unexpected payload format: missing 'totalDataChart'")

    series = payload["totalDataChart"]
    # Expect series as list of [timestamp, value]
    by_day: dict[date, list[float]] = defaultdict(list)
    for row in series:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        ts, val = row[0], row[1]
        try:
            d = parse_utc_date(ts)
        except Exception:
            continue
        if val is None:
            continue
        try:
            v = float(val)
        except Exception:
            continue
        if START_DATE <= d <= END_DATE:
            by_day[d].append(v)

    # Build daily values for each date in the window
    daily_values: list[tuple[date, float]] = []
    missing_days: list[date] = []
    cur = START_DATE
    while cur <= END_DATE:
        vals = by_day.get(cur, [])
        if vals:
            # If multiple entries per day, average them
            daily_values.append((cur, sum(vals) / len(vals)))
        else:
            missing_days.append(cur)
        cur += timedelta(days=1)

    if missing_days:
        print("Warning: missing daily data for these UTC dates:")
        for d in missing_days:
            print(f"  - {d.isoformat()}")
        if not daily_values:
            raise RuntimeError("No data available in the requested window.")

    # Print intermediary per-day values before averaging
    print(f"Per-day Base chain daily revenue (USD), UTC dates {START_DATE} to {END_DATE}:")
    for d, v in sorted(daily_values, key=lambda x: x[0]):
        print(f"  {d.isoformat()}: ${v:,.2f}")

    avg_usd = sum(v for _, v in daily_values) / len(daily_values)
    avg_int = int(round(avg_usd))

    print("\n30-day trailing average (Base daily revenue):")
    print(f"  Average: ${avg_usd:,.2f}  -> ${avg_int}")


if __name__ == "__main__":
    main()

