#!/usr/bin/env python3
"""
Fetch historical TVL series for one or more DefiLlama chains and
report the TVL in USD at 2025-09-26 00:00:00 UTC for each chain.

Usage examples:
  python3 @2025-09-26-kpi/compute_chain_tvl_at_2025_09_26_utc00.py Base
  python3 @2025-09-26-kpi/compute_chain_tvl_at_2025_09_26_utc00.py Solana "Hyperliquid L1"

For each chain, prints the data point used and the final integer USD value.
Raw JSON is saved per chain for traceability.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import quote
from urllib.request import urlopen, Request


BASE_ENDPOINT = "https://api.llama.fi/v2/historicalChainTvl/"
DATA_DIR = os.path.dirname(__file__)

TARGET_DT = datetime(2025, 9, 26, 0, 0, 0, tzinfo=timezone.utc)
TARGET_TS = int(TARGET_DT.timestamp())


def sanitize_filename_fragment(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_")


def fetch_chain_series(chain: str) -> List[Dict[str, Any]]:
    chain_path = quote(chain, safe="")
    endpoint = BASE_ENDPOINT + chain_path
    req = Request(endpoint, headers={"User-Agent": "metric-script/1.0"})
    with urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    raw_path = os.path.join(
        DATA_DIR, f"defillama_chain_{sanitize_filename_fragment(chain)}_tvl_raw.json"
    )
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def extract_tvl_value(row: Dict[str, Any]) -> float | None:
    for key in ("tvl", "totalLiquidityUSD", "value"):
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except Exception:
                return None
    return None


def find_exact_entry(series: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    for row in series:
        ts = row.get("date")
        if ts is None:
            continue
        try:
            ts = int(ts)
        except Exception:
            continue
        if ts == TARGET_TS:
            return row
    return None


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Report chain TVL at 2025-09-26 00:00 UTC")
    ap.add_argument("chains", nargs="+", help="DefiLlama chain names (e.g., Base, Solana, 'Hyperliquid L1')")
    args = ap.parse_args(argv)

    for chain in args.chains:
        print(f"\n=== {chain} ===")
        try:
            series = fetch_chain_series(chain)
        except Exception as e:
            print(f"Error fetching series for {chain}: {e}")
            continue

        if not isinstance(series, list):
            print(f"Unexpected payload for {chain}: expected a list of entries")
            continue

        match = find_exact_entry(series)
        if match is None:
            print("No exact entry at 2025-09-26 00:00:00Z found for this chain.")
            # Show nearest few for transparency
            candidates = []
            for row in series:
                ts = row.get("date")
                try:
                    ts = int(ts)
                except Exception:
                    continue
                candidates.append((abs(ts - TARGET_TS), ts, row))
            if not candidates:
                print("  Series is empty or malformed.")
                continue
            candidates.sort(key=lambda x: x[0])
            for i, (_, ts, row) in enumerate(candidates[:3], start=1):
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                tvl = extract_tvl_value(row)
                print(f"  Candidate {i}: {dt.isoformat()} -> ${tvl:,.2f} (ts={ts})")
            # Proceed with the nearest for usability, but note mismatch
            match = candidates[0][2]
            print("Using nearest available candidate above.")

        ts = int(match.get("date"))
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        tvl = extract_tvl_value(match)
        if tvl is None:
            print("  Matched entry lacks a TVL value.")
            continue

        print("Data point used:")
        print(f"  Timestamp: {ts} -> {dt.isoformat()}")
        print(f"  TVL (USD): ${tvl:,.2f}")

        tvl_int = int(round(tvl))
        print("Result:")
        print(f"  {chain} TVL at 2025-09-26 00:00 UTC: ${tvl:,.2f} -> ${tvl_int}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

