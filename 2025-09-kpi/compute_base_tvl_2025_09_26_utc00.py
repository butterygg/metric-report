#!/usr/bin/env python3
"""
Fetch Base chain historical TVL series and report the TVL in USD
on 2025-09-26 at 00:00:00 UTC. Prints the matched data point used
before outputting the final integer USD value.

Endpoint:
  https://api.llama.fi/v2/historicalChainTvl/Base
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.request import urlopen, Request


ENDPOINT = "https://api.llama.fi/v2/historicalChainTvl/Base"
DATA_DIR = os.path.dirname(__file__)
RAW_PATH = os.path.join(DATA_DIR, "defillama_chain_base_tvl_raw.json")

TARGET_DT = datetime(2025, 9, 26, 0, 0, 0, tzinfo=timezone.utc)
TARGET_TS = int(TARGET_DT.timestamp())


def fetch_and_save_raw() -> List[Dict[str, Any]]:
    req = Request(ENDPOINT, headers={"User-Agent": "metric-script/1.0"})
    with urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    # Persist raw payload
    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def load_raw_from_disk() -> List[Dict[str, Any]] | None:
    if not os.path.exists(RAW_PATH):
        return None
    with open(RAW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_tvl_value(row: Dict[str, Any]) -> float | None:
    # DefiLlama series may use 'tvl' or 'totalLiquidityUSD'
    for key in ("tvl", "totalLiquidityUSD", "value"):
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except Exception:
                return None
    return None


def main() -> None:
    try:
        series = fetch_and_save_raw()
    except Exception as e:
        local = load_raw_from_disk()
        if local is None:
            raise RuntimeError(f"Failed to fetch data and no local raw file found: {e}")
        print(f"Warning: network fetch failed ({e}); using cached raw data at {RAW_PATH}")
        series = local

    if not isinstance(series, list):
        raise ValueError("Unexpected payload format: expected a list of entries")

    # Find exact match for 2025-09-26 00:00 UTC by timestamp
    match = None
    for row in series:
        ts = row.get("date")
        if ts is None:
            continue
        try:
            ts = int(ts)
        except Exception:
            continue
        if ts == TARGET_TS:
            match = row
            break

    if match is None:
        # Provide context: closest surrounding points, if any
        print("No exact entry found at 2025-09-26 00:00:00Z. Searching for nearest entries...")
        # Sort by absolute distance to target
        candidates = []
        for row in series:
            ts = row.get("date")
            try:
                ts = int(ts)
            except Exception:
                continue
            candidates.append((abs(ts - TARGET_TS), ts, row))
        if not candidates:
            raise RuntimeError("Historical series is empty or malformed.")
        candidates.sort(key=lambda x: x[0])
        # Print top 3 nearest entries for transparency
        for i, (_, ts, row) in enumerate(candidates[:3], start=1):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            tvl = extract_tvl_value(row)
            print(f"  Candidate {i}: {dt.isoformat()} -> ${tvl:,.2f} (ts={ts})")
        # Use the closest if exact not available
        match = candidates[0][2]

    ts = int(match.get("date"))
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    tvl = extract_tvl_value(match)
    if tvl is None:
        raise RuntimeError("Matched entry lacks a TVL value.")

    # Print the data point used (intermediary value)
    print("Data point used:")
    print(f"  Timestamp: {ts} -> {dt.isoformat()}")
    print(f"  TVL (USD): ${tvl:,.2f}")

    tvl_int = int(round(tvl))
    print("\nResult:")
    print(f"  Base chain TVL at 2025-09-26 00:00 UTC: ${tvl:,.2f} -> ${tvl_int}")


if __name__ == "__main__":
    main()

