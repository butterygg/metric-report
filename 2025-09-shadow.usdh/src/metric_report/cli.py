from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, getcontext, ROUND_FLOOR
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Arithmetic precision for Decimal operations
getcontext().prec = 40

API_URL = "https://api.hyperliquid.xyz/info"
MS_MINUTE = 60_000
WINDOW_MINUTES = 12 * 60  # 720
MAX_CONSEC_MISSING = 60


@dataclass(frozen=True)
class Anchors:
    decision_ms: int
    start_exact_ms: int
    start_ms: int
    end_ms: int
    earliest_answerable_ms: int


def _now_ms() -> int:
    return int(time.time() * 1000)


def iso_to_ms(s: str) -> int:
    s_norm = s.strip()
    if s_norm.endswith("Z"):
        s_norm = s_norm[:-1] + "+00:00"
    dt = datetime.fromisoformat(s_norm)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ceil_to_minute(ms: int) -> int:
    return ((ms + MS_MINUTE - 1) // MS_MINUTE) * MS_MINUTE


def compute_anchors(decision_ms: int) -> Anchors:
    start_exact = decision_ms + 120 * MS_MINUTE
    start_ms = ceil_to_minute(start_exact)
    end_ms = start_ms + WINDOW_MINUTES * MS_MINUTE
    earliest = end_ms + 5 * MS_MINUTE
    return Anchors(
        decision_ms=decision_ms,
        start_exact_ms=start_exact,
        start_ms=start_ms,
        end_ms=end_ms,
        earliest_answerable_ms=earliest,
    )


def post_info(payload: Dict[str, Any]) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = Request(API_URL, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_spot_meta(artifacts_dir: str | None) -> Dict[str, Any]:
    meta = post_info({"type": "spotMeta"})
    if artifacts_dir is not None:
        with open(f"{artifacts_dir}/spotMeta.json", "w") as f:
            json.dump(meta, f, indent=2)
    return meta


def resolve_hype_usdc_coin(meta: Dict[str, Any]) -> str:
    tokens = meta.get("tokens", [])
    universe = meta.get("universe", [])

    name_to_index: Dict[str, int] = {}
    for t in tokens:
        name = t.get("name")
        idx = t.get("index")
        if isinstance(name, str) and isinstance(idx, int):
            name_to_index[name] = idx

    # Primary path: match tokens indices
    hype_idx = name_to_index.get("HYPE")
    usdc_idx = name_to_index.get("USDC")
    if hype_idx is not None and usdc_idx is not None:
        for pair in universe:
            toks = pair.get("tokens")
            if toks == [hype_idx, usdc_idx]:
                pair_idx = pair.get("index")
                if isinstance(pair_idx, int):
                    return f"@{pair_idx}"

    # Fallback: use pair name if present in meta
    for pair in universe:
        if pair.get("name") == "HYPE/USDC":
            pair_idx = pair.get("index")
            if isinstance(pair_idx, int):
                return f"@{pair_idx}"

    # As a last resort, allow literal name if universe provides it
    for pair in universe:
        if pair.get("name") == "HYPE/USDC":
            return "HYPE/USDC"

    raise RuntimeError("Could not resolve HYPE/USDC spot pair from spotMeta.")


def fetch_candles_paged(coin: str, start_ms: int, end_ms: int) -> List[Dict[str, Any]]:
    all_items: List[Dict[str, Any]] = []
    cursor = start_ms
    last_progress = None
    while cursor < end_ms:
        body = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": "1m",
                "startTime": cursor,
                "endTime": end_ms,
            },
        }
        batch = post_info(body)
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected candleSnapshot response type")
        if not batch:
            break
        all_items.extend(batch)
        last_T = int(batch[-1]["T"])
        if last_progress is not None and last_T <= last_progress:
            break
        last_progress = last_T
        cursor = last_T + 1
    return all_items


def fetch_prev_minute_close(coin: str, first_minute_ms: int) -> Optional[Decimal]:
    start = first_minute_ms - MS_MINUTE
    end = first_minute_ms
    body = {
        "type": "candleSnapshot",
        "req": {"coin": coin, "interval": "1m", "startTime": start, "endTime": end},
    }
    batch = post_info(body)
    if isinstance(batch, list) and batch:
        return Decimal(str(batch[-1]["c"]))
    return None


def build_minute_series(
    candles: List[Dict[str, Any]], start_ms: int, end_ms: int, prev_close: Optional[Decimal]
) -> Tuple[List[int], List[Decimal], List[str]]:
    # Index candles by their start time 't' for 1m interval only
    by_start: Dict[int, Decimal] = {}
    for c in candles:
        if c.get("i") == "1m" and "t" in c and "c" in c:
            by_start[int(c["t"])] = Decimal(str(c["c"]))

    grid = list(range(start_ms, end_ms, MS_MINUTE))
    closes: List[Decimal] = []
    sources: List[str] = []
    missing_streak = 0
    last_close = prev_close

    for t in grid:
        px = by_start.get(t)
        if px is not None:
            closes.append(px)
            sources.append("actual")
            missing_streak = 0
            last_close = px
        else:
            missing_streak += 1
            if last_close is None:
                raise RuntimeError(
                    "First minute missing and no previous close available for carry-forward."
                )
            if missing_streak > MAX_CONSEC_MISSING:
                raise RuntimeError(
                    f"> {MAX_CONSEC_MISSING} consecutive minutes missing; not answerable yet."
                )
            closes.append(last_close)
            sources.append("filled")

    if len(closes) != WINDOW_MINUTES:
        raise RuntimeError(f"Expected {WINDOW_MINUTES} minutes, got {len(closes)}")

    return grid, closes, sources


def round_half_up_cents(value_usd: Decimal) -> int:
    x = value_usd * Decimal(100)
    return int((x + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR))


def write_candles_artifact(artifacts_dir: str, items: List[Dict[str, Any]]) -> None:
    with open(f"{artifacts_dir}/candles.json", "w") as f:
        json.dump(items, f, indent=2)


def write_closes_csv(
    artifacts_dir: str, grid: List[int], closes: List[Decimal], sources: List[str]
) -> None:
    path = f"{artifacts_dir}/closes.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t_start_ms", "t_start_iso", "close", "source"])
        for t, px, src in zip(grid, closes, sources):
            writer.writerow([t, ms_to_iso(t), str(px), src])


def write_result_json(artifacts_dir: str, anchors: Anchors, coin: str, twap: Decimal, cents: int) -> None:
    data = {
        "decision_time_ms": anchors.decision_ms,
        "decision_time_iso": ms_to_iso(anchors.decision_ms),
        "observation_start_ms": anchors.start_ms,
        "observation_start_iso": ms_to_iso(anchors.start_ms),
        "observation_end_ms": anchors.end_ms,
        "observation_end_iso": ms_to_iso(anchors.end_ms),
        "earliest_answerable_ms": anchors.earliest_answerable_ms,
        "earliest_answerable_iso": ms_to_iso(anchors.earliest_answerable_ms),
        "n_minutes": WINDOW_MINUTES,
        "twap_usd": str(twap),
        "cents_uint": cents,
        "coin": coin,
    }
    with open(f"{artifacts_dir}/result.json", "w") as f:
        json.dump(data, f, indent=2)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Compute 12h TWAP (HYPE/USDC spot) from Hyperliquid Info API and write artifacts."
        )
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--decision-time",
        type=str,
        help="Decision time T_d as ISO8601 Z, e.g. 2025-09-18T17:03:00Z",
    )
    g.add_argument(
        "--decision-time-ms",
        type=str,
        help="Decision time T_d as epoch milliseconds (UTC)",
    )
    p.add_argument(
        "--artifacts",
        type=str,
        default="artifacts",
        help="Directory to write artifacts (default: artifacts)",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging to stderr",
    )
    p.add_argument(
        "--allow-early",
        action="store_true",
        help="Allow computation before earliest-answerable time (Te + 5m)",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    artifacts_dir: str = args.artifacts
    # Ensure dir exists
    try:
        import os

        os.makedirs(artifacts_dir, exist_ok=True)
    except Exception as e:
        print(f"Error creating artifacts dir: {e}", file=sys.stderr)
        return 1

    # Parse decision time
    if args.decision_time:
        decision_ms = iso_to_ms(args.decision_time)
    else:
        decision_ms = int(args.decision_time_ms)

    anchors = compute_anchors(decision_ms)

    # Earliest-answerable check unless overridden
    now_ms = _now_ms()
    if now_ms < anchors.earliest_answerable_ms and not args.allow_early:
        print(
            f"answered too soon: now={ms_to_iso(now_ms)} < earliest={ms_to_iso(anchors.earliest_answerable_ms)}",
            file=sys.stderr,
        )
        return 2

    try:
        # spotMeta
        meta = fetch_spot_meta(artifacts_dir)
        coin = resolve_hype_usdc_coin(meta)

        # Optional seed close for first-minute missing case
        prev_close = fetch_prev_minute_close(coin, anchors.start_ms)

        # Paged candle fetch over [Ts, Te)
        candles = fetch_candles_paged(coin, anchors.start_ms, anchors.end_ms)
        write_candles_artifact(artifacts_dir, candles)

        # Build grid and closes with carry-forward
        grid, closes, sources = build_minute_series(candles, anchors.start_ms, anchors.end_ms, prev_close)
        write_closes_csv(artifacts_dir, grid, closes, sources)

        # TWAP
        total = sum(closes, start=Decimal(0))
        if len(closes) != WINDOW_MINUTES:
            raise RuntimeError(f"Expected {WINDOW_MINUTES} minutes, got {len(closes)}")
        twap = total / Decimal(len(closes))
        cents = round_half_up_cents(twap)

        write_result_json(artifacts_dir, anchors, coin, twap, cents)

        # Final required stdout: cents integer only
        print(cents)
        return 0

    except (HTTPError, URLError) as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main_entry() -> None:
    sys.exit(main())

