#!/usr/bin/env python3
"""
Compute the 30-day trailing average (up to 2025-09-25, inclusive)
of ETH.STORE APR ("apr") from beaconcha.in API, printing each
daily observation before averaging. Each day is keyed by the UTC
calendar date of the `day_end` field. The average is returned in
integer basis points, rounded to the nearest integer.

Endpoint per day:
  https://beaconcha.in/api/v1/ethstore/{day}   where {day} = YYYY-MM-DD

Notes:
- Uses only the daily `apr` observations (no precomputed rolling averages).
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any, Dict
from urllib.request import Request, urlopen


# Numeric day index endpoint, e.g., https://beaconcha.in/api/v1/ethstore/1706
TEMPLATE = "https://beaconcha.in/api/v1/ethstore/{day}"
DATA_DIR = os.path.dirname(__file__)
RAW_PATH = os.path.join(DATA_DIR, "beaconchain_ethstore_raw.json")

END_DATE = date(2025, 9, 25)  # inclusive
WINDOW_DAYS = 30
START_DATE = END_DATE - timedelta(days=WINDOW_DAYS - 1)


def fetch_day_payload(day_id: int) -> Dict[str, Any]:
    url = TEMPLATE.format(day=day_id)
    headers = {"User-Agent": "metric-script/1.0", "Accept": "application/json"}
    api_key = os.getenv("BEACONCHAIN_API_KEY")
    if api_key:
        # Support both header and query param styles for compatibility
        headers["X-API-KEY"] = api_key
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}apikey={api_key}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as resp:
        return json.load(resp)


def extract_apr_and_day_end(payload: Dict[str, Any]) -> list[tuple[float, str]]:
    """Return list of (apr, day_end_iso) observations found in payload."""
    results: list[tuple[float, str]] = []
    obj: Any = payload.get("data", payload)
    def one(entry: Dict[str, Any]):
        apr = entry.get("apr")
        day_end = entry.get("day_end") or entry.get("dayEnd") or entry.get("date")
        try:
            apr_val = float(apr) if apr is not None else None
        except Exception:
            apr_val = None
        if apr_val is None or not day_end:
            return
        results.append((apr_val, str(day_end)))
    if isinstance(obj, dict):
        one(obj)
    elif isinstance(obj, list):
        for it in obj:
            if isinstance(it, dict):
                one(it)
    return results


def parse_utc_date_from_iso(iso_str: str) -> date | None:
    try:
        s = iso_str.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.date()
    except Exception:
        return None


def discover_and_fetch_window() -> Dict[str, Any]:
    """Discover numeric day IDs that fall within the UTC window by
    scanning around a reasonable range, then fetch and return a map
    from day_id to payload for those in-window entries.

    Strategy: start from an ID guess (e.g., 1700) and increment
    until day_end exceeds END_DATE; collect entries where day_end
    is within [START_DATE, END_DATE].
    """
    collected: Dict[str, Any] = {}
    # Conservative bounds to avoid excessive requests while covering the window
    start_id = 1700
    max_id = 1850
    for day_id in range(start_id, max_id + 1):
        try:
            payload = fetch_day_payload(day_id)
        except Exception as e:
            # Keep note of failures but continue
            collected[str(day_id)] = {"error": str(e)}
            time.sleep(0.1)
            continue
        # Parse to see if it contains a usable day_end
        pairs = extract_apr_and_day_end(payload)
        # Choose the first if multiple
        if not pairs:
            # Store anyway for traceability
            collected[str(day_id)] = payload
            time.sleep(0.1)
            continue
        apr, day_end_str = pairs[0]
        d = parse_utc_date_from_iso(day_end_str)
        # Persist payload regardless
        collected[str(day_id)] = payload
        if d is None:
            time.sleep(0.1)
            continue
        if d < START_DATE:
            time.sleep(0.05)
            continue
        if d > END_DATE:
            # We can break once we have passed the window and have collected enough
            # to be safe; still keep this payload in the raw file.
            break
        time.sleep(0.05)
    return collected


def load_raw() -> Dict[str, Any] | None:
    if not os.path.exists(RAW_PATH):
        return None
    with open(RAW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    # Always try fresh fetch; if fails, fallback to cached raw
    try:
        raw_window = discover_and_fetch_window()
        with open(RAW_PATH, "w", encoding="utf-8") as f:
            json.dump(raw_window, f, ensure_ascii=False, indent=2)
    except Exception as e:
        cached = load_raw()
        if cached is None:
            raise RuntimeError(f"Failed to fetch data and no local raw file found: {e}")
        print(f"Warning: network fetch failed ({e}); using cached raw data at {RAW_PATH}")
        raw_window = cached

    # Aggregate APR values by UTC date of day_end
    by_day: dict[date, list[float]] = defaultdict(list)
    for key, payload in raw_window.items():
        if not isinstance(payload, dict):
            continue
        pairs = extract_apr_and_day_end(payload)
        for apr, day_end_str in pairs:
            d = parse_utc_date_from_iso(day_end_str)
            if d is None:
                continue
            if START_DATE <= d <= END_DATE:
                by_day[d].append(apr)

    # Build daily series across the full window (UTC dates)
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
        print("Warning: missing daily data for these UTC dates (day_end):")
        for d in missing_days:
            print(f"  - {d.isoformat()}")
        if not daily_values:
            raise RuntimeError("No data available within the requested window.")

    # Print per-day APR values before averaging
    print(f"Per-day ETH.STORE APR (percent), by day_end UTC date {START_DATE} to {END_DATE}:")
    for d, apr_frac in sorted(daily_values, key=lambda x: x[0]):
        percent = apr_frac * 100.0
        bps = round(apr_frac * 10000.0)
        print(f"  {d.isoformat()}: {percent:.6f}%  (~{bps} bps)")

    avg_fraction = mean(v for _, v in daily_values)
    avg_bps = int(round(avg_fraction * 10000.0))

    print("\n30-day trailing average (ETH.STORE APR):")
    print(f"  Average: {(avg_fraction*100):.6f}%  -> {avg_bps} bps")


if __name__ == "__main__":
    main()
