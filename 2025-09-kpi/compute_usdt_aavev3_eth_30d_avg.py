#!/usr/bin/env python3
"""
Compute the 30-day trailing average (up to 2025-09-25, inclusive)
of USDT Aave V3 Ethereum supply APY excluding rewards (base APY),
using DefiLlama Yields chart endpoint. Prints each daily value
before averaging (treated by UTC calendar date) and outputs the
average in integer basis points.

Endpoint:
  https://yields.llama.fi/chart/f981a304-bb6c-45b8-b0c5-fd2f515ad23a
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date
from statistics import mean
from urllib.request import urlopen, Request


ENDPOINT = "https://yields.llama.fi/chart/f981a304-bb6c-45b8-b0c5-fd2f515ad23a"
DATA_DIR = os.path.dirname(__file__)
RAW_PATH = os.path.join(DATA_DIR, "defillama_yields_usdt_aavev3_eth_raw.json")

END_DATE = date(2025, 9, 25)  # inclusive
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
    # Accept integer seconds since epoch, numeric string, or ISO 8601 string
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
    raise ValueError(f"Unsupported timestamp value: {ts_val!r}")


def main() -> None:
    try:
        payload = fetch_and_save_raw()
    except Exception as e:
        local = load_raw_from_disk()
        if local is None:
            raise RuntimeError(f"Failed to fetch data and no local raw file found: {e}")
        print(f"Warning: network fetch failed ({e}); using cached raw data at {RAW_PATH}")
        payload = local

    if not isinstance(payload, dict) or "data" not in payload:
        raise ValueError("Unexpected payload format: missing 'data'")

    points = payload["data"]
    by_day: dict[date, list[float]] = defaultdict(list)

    for pt in points:
        ts = pt.get("timestamp") or pt.get("datetime") or pt.get("time")
        apy_base = pt.get("apyBase")
        if ts is None or apy_base is None:
            continue
        try:
            d = parse_utc_date(ts)
        except Exception:
            continue
        if START_DATE <= d <= END_DATE:
            try:
                val = float(apy_base)
            except Exception:
                continue
            by_day[d].append(val)

    daily_values: list[tuple[date, float]] = []
    missing_days: list[date] = []
    cur = START_DATE
    while cur <= END_DATE:
        vals = by_day.get(cur, [])
        if vals:
            daily_values.append((cur, mean(vals)))
        else:
            missing_days.append(cur)
        cur += timedelta(days=1)

    if missing_days:
        print("Warning: missing daily data for these UTC dates:")
        for d in missing_days:
            print(f"  - {d.isoformat()}")
        if len(daily_values) == 0:
            raise RuntimeError("No data available within the requested window.")

    print(f"Per-day base APY values (percent), UTC dates {START_DATE} to {END_DATE}:")
    for d, v in sorted(daily_values, key=lambda x: x[0]):
        bps = round(v * 100)
        print(f"  {d.isoformat()}: {v:.6f}%  (~{bps} bps)")

    avg_percent = mean(v for _, v in daily_values)
    avg_bps = int(round(avg_percent * 100))  # 1% == 100 bps

    print("\n30-day trailing average (base APY, no rewards):")
    print(f"  Average: {avg_percent:.6f}%  -> {avg_bps} bps")


if __name__ == "__main__":
    main()

