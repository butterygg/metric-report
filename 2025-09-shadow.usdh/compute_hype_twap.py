#!/usr/bin/env python3
# compute_hype_twap.py
#
# Computes the 12h TWAP for HYPE/USDC spot on Hyperliquid, starting exactly
# 120 minutes after a decision time, using 1-minute CLOSE prices from the Info API.
# Output: unsigned integer CENTS = round_half_up(TWAP * 100).
#
# Artifacts saved:
#  - artifacts/spotMeta.json
#  - artifacts/candles.json (concatenated API candles)
#  - artifacts/closes.csv (t_start_ms,t_start_iso,close,source[actual|filled])
#  - artifacts/result.json (TWAP USD, CENTS, times)
#
# Usage examples:
#   python compute_hype_twap.py --decision-time "2025-09-12T16:00:00Z"
#   python compute_hype_twap.py --decision-time-ms 1757673600000
#
# Notes:
#  - If T_d is not exactly on a minute boundary, we ceil to the next minute
#    for the first included 1m candle (API candles are minute-aligned).
#  - If >60 consecutive minutes are missing, we abort (not answerable yet).
#  - Half-up rounding implemented as floor(x + 0.5) for x = TWAP*100 (>0).

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal, getcontext, ROUND_FLOOR

import requests

API_URL = "https://api.hyperliquid.xyz/info"
SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json"})

# High precision for Decimal arithmetic on sums/averages
getcontext().prec = 40

MS_MINUTE = 60_000
TWELVE_HOURS_MIN = 12 * 60
WINDOW_MINUTES = 720  # 12h * 60
MAX_CONSEC_MISSING = 60  # per rules

def parse_args():
    p = argparse.ArgumentParser(description="Compute 12h TWAP (HYPE/USDC spot) per Reality rules.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--decision-time", type=str,
                   help="Decision time T_d as ISO 8601 (e.g., 2025-09-12T16:00:00Z).")
    g.add_argument("--decision-time-ms", type=str,
                   help="Decision time T_d as milliseconds since epoch (UTC).")
    p.add_argument("--artifacts", type=str, default=None,
                   help="Directory to save artifacts (default: artifacts_twap_<timestamp>).")
    p.add_argument("--allow-early", action="store_true",
                   help="Compute even if we're before T_e + 5 minutes (for dry runs).")
    p.add_argument("--verbose", action="store_true", help="Extra logging.")
    return p.parse_args()

def iso_to_ms(s: str) -> int:
    # Accept trailing 'Z' or explicit offset; normalize to UTC
    s_norm = s.strip()
    if s_norm.endswith("Z"):
        s_norm = s_norm[:-1] + "+00:00"
    dt = datetime.fromisoformat(s_norm)
    if dt.tzinfo is None:
        # treat as UTC if naive, though inputs should be UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def ceil_to_minute(ms: int) -> int:
    return ((ms + MS_MINUTE - 1) // MS_MINUTE) * MS_MINUTE

def post_info(payload: dict):
    r = SESSION.post(API_URL, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_spot_meta(artifacts_dir: str, verbose=False) -> dict:
    body = {"type": "spotMeta"}
    meta = post_info(body)
    if artifacts_dir:
        with open(os.path.join(artifacts_dir, "spotMeta.json"), "w") as f:
            json.dump(meta, f, indent=2)
    if verbose:
        print("Fetched spotMeta.")
    return meta

def resolve_hype_usdc_coin(meta: dict, verbose=False) -> str:
    # Find token indices for HYPE and USDC, then find the universe entry with [HYPE_idx, USDC_idx]
    tokens = meta.get("tokens", [])
    universe = meta.get("universe", [])
    name_to_index = {t["name"]: t["index"] for t in tokens if "name" in t and "index" in t}

    if "HYPE" not in name_to_index or "USDC" not in name_to_index:
        # Fallback: try to match by pair name directly (if present)
        for pair in universe:
            if pair.get("name") == "HYPE/USDC":
                idx = pair["index"]
                coin = f"@{idx}"
                if verbose:
                    print(f"Resolved coin from pair name: {coin}")
                return coin
        raise RuntimeError("Could not find HYPE or USDC indices in spotMeta tokens.")

    hype_idx = name_to_index["HYPE"]
    usdc_idx = name_to_index["USDC"]

    for pair in universe:
        toks = pair.get("tokens")
        if toks == [hype_idx, usdc_idx]:
            idx = pair["index"]
            # For spot, '@{index}' is the canonical coin identifier (except PURR, which uses 'PURR/USDC')
            coin = f"@{idx}"
            if verbose:
                print(f"Resolved coin via tokens mapping: tokens={toks} index={idx} -> coin={coin}")
            return coin

    # Fallback by name if present
    for pair in universe:
        if pair.get("name") == "HYPE/USDC":
            idx = pair["index"]
            coin = f"@{idx}"
            if verbose:
                print(f"Resolved coin via fallback name: index={idx} -> coin={coin}")
            return coin

    raise RuntimeError("Could not resolve HYPE/USDC spot pair in spotMeta universe.")

def fetch_candles(coin: str, start_ms: int, end_ms: int, interval="1m", verbose=False):
    """
    Paginate candleSnapshot until we cover [start_ms, end_ms).
    The Info endpoint pages time-ranged responses (~500 items per page). We advance using last 'T'.
    """
    all_candles = []
    cursor = start_ms
    last_progress = None

    while cursor < end_ms:
        body = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms
            }
        }
        batch = post_info(body)
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected candleSnapshot response: {batch}")
        if not batch:
            # No more data; break to avoid infinite loop
            break

        all_candles.extend(batch)

        # Advance cursor using the last candle's 'T' (end timestamp); add +1ms to avoid duplication
        last_T = int(batch[-1]["T"])
        if verbose:
            print(f"Fetched {len(batch)} candles; advancing cursor from {cursor} to {last_T}+1")
        if last_progress is not None and last_T <= last_progress:
            # Defensive: no forward progress; break
            break
        last_progress = last_T
        cursor = last_T + 1

        # Guard: if we're already at or past end_ms, stop
        if cursor >= end_ms:
            break

    return all_candles

def fetch_prev_minute_close(coin: str, first_minute_ms: int):
    """
    Get the close of the minute immediately preceding first_minute_ms, if available.
    """
    start = first_minute_ms - MS_MINUTE
    end = first_minute_ms
    body = {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1m", "startTime": start, "endTime": end}}
    batch = post_info(body)
    if isinstance(batch, list) and batch:
        # Expect exactly one candle
        return Decimal(batch[-1]["c"])
    return None

def build_minute_series(candles: list, start_ms: int, end_ms: int, prev_close: Decimal, verbose=False):
    """
    Build a 1-minute CLOSE series on the exact minute grid [start_ms, end_ms) with step=60_000.
    Fill missing minutes by carry-forward (previous close). If >60 consecutive missing, abort.
    """
    # Map candles by their start time 't'
    idx = {}
    for c in candles:
        # Only keep 1m for safety; ignore any off-interval items
        if c.get("i") == "1m":
            t = int(c["t"])
            idx[t] = Decimal(c["c"])

    grid = list(range(start_ms, end_ms, MS_MINUTE))
    closes = []
    sources = []
    missing_streak = 0
    last_close = prev_close

    for t in grid:
        if t in idx:
            px = idx[t]
            closes.append(px)
            sources.append("actual")
            missing_streak = 0
            last_close = px
        else:
            # Missing minute
            missing_streak += 1
            if last_close is None:
                # Try to prevent edge case: no previous close at very first minute
                raise RuntimeError("First minute missing and no previous close available for carry-forward.")
            if missing_streak > MAX_CONSEC_MISSING:
                raise RuntimeError(f"> {MAX_CONSEC_MISSING} consecutive minutes missing; not answerable yet.")
            closes.append(last_close)
            sources.append("filled")

    if len(closes) != WINDOW_MINUTES:
        raise RuntimeError(f"Expected {WINDOW_MINUTES} minutes, got {len(closes)}.")

    return grid, closes, sources

def round_half_up_cents(value_usd: Decimal) -> int:
    # Implements floor(x + 0.5) for x > 0, where x = TWAP * 100
    x = (value_usd * Decimal(100))
    return int((x + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR))

def main():
    args = parse_args()

    # Determine artifacts path
    if args.artifacts:
        artifacts_dir = args.artifacts
    else:
        tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        artifacts_dir = f"artifacts_twap_{tag}"
    os.makedirs(artifacts_dir, exist_ok=True)

    # Parse decision time T_d
    if args.decision_time:
        T_d_ms = iso_to_ms(args.decision_time)
    else:
        # millisecond string or int
        T_d_ms = int(args.decision_time_ms)

    # Compute anchors
    Ts_exact = T_d_ms + 120 * 60 * 1000  # +120 minutes
    Ts = ceil_to_minute(Ts_exact)        # align to next minute boundary for 1m candles
    Te = Ts + TWELVE_HOURS_MIN * MS_MINUTE

    # Optional earliest-answerable check (Te + 5 min)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    earliest_answerable = Te + 5 * MS_MINUTE
    if now_ms < earliest_answerable and not args.allow_early:
        print(f"[Abort] Earliest answerable time not reached. Now={ms_to_iso(now_ms)}, "
              f"need >= {ms_to_iso(earliest_answerable)}. Use --allow-early to override.", file=sys.stderr)
        sys.exit(2)

    if args.verbose:
        print(f"T_d = {ms_to_iso(T_d_ms)} ({T_d_ms})")
        print(f"T_s_exact = {ms_to_iso(Ts_exact)} ({Ts_exact})")
        print(f"T_s (minute-aligned) = {ms_to_iso(Ts)} ({Ts})")
        print(f"T_e = {ms_to_iso(Te)} ({Te})")

    # Resolve HYPE/USDC spot coin identifier
    meta = fetch_spot_meta(artifacts_dir, verbose=args.verbose)
    coin = resolve_hype_usdc_coin(meta, verbose=args.verbose)

    # Fetch a previous-minute close for carry-forward if first minute is missing
    prev_close = fetch_prev_minute_close(coin, Ts)

    # Fetch candles over [Ts, Te)
    candles = fetch_candles(coin, Ts, Te, interval="1m", verbose=args.verbose)

    # Save raw candles
    with open(os.path.join(artifacts_dir, "candles.json"), "w") as f:
        json.dump(candles, f, indent=2)

    # Build minute-aligned CLOSE series with carry-forward
    grid, closes, sources = build_minute_series(candles, Ts, Te, prev_close, verbose=args.verbose)

    # Save closes CSV
    csv_path = os.path.join(artifacts_dir, "closes.csv")
    with open(csv_path, "w") as f:
        f.write("t_start_ms,t_start_iso,close,source\n")
        for t, px, src in zip(grid, closes, sources):
            f.write(f"{t},{ms_to_iso(t)},{str(px)},{src}\n")

    # Compute simple average TWAP
    total = sum(closes, start=Decimal(0))
    N = Decimal(len(closes))
    if len(closes) != WINDOW_MINUTES:
        raise RuntimeError(f"Expected {WINDOW_MINUTES} minutes, got {len(closes)}.")
    twap = total / N

    # Final integer cents with half-up rounding
    cents = round_half_up_cents(twap)

    # Save result.json
    result = {
        "decision_time_ms": T_d_ms,
        "decision_time_iso": ms_to_iso(T_d_ms),
        "observation_start_ms": Ts,
        "observation_start_iso": ms_to_iso(Ts),
        "observation_end_ms": Te,
        "observation_end_iso": ms_to_iso(Te),
        "earliest_answerable_ms": earliest_answerable,
        "earliest_answerable_iso": ms_to_iso(earliest_answerable),
        "n_minutes": int(N),
        "twap_usd": str(twap),
        "cents_uint": cents,
        "coin": coin,
    }
    with open(os.path.join(artifacts_dir, "result.json"), "w") as f:
        json.dump(result, f, indent=2)

    # Required final output for Reality answer
    print(cents)

if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"HTTP error: {e} | response={getattr(e, 'response', None) and getattr(e.response, 'text', '')}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
