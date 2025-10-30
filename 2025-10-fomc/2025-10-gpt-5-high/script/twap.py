#!/usr/bin/env python3
"""
CLI tool to compute 12-hour TWAP for Binance spot symbols (BTCUSDT or ETHUSDT).

Follows spec in ../_spec/01-binance-twap.md.

Usage examples:
  python3 script/twap.py --symbol BTCUSDT
  python3 script/twap.py --symbol ETHUSDT --strict-final

The tool prints to stdout and also writes JSON diagnostics and raw klines.
It also creates a timestamped run directory inside this package directory
named "<ISO8601-UTC-timestamp>-<model_name>" by default.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    # stdlib in 3.11+
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
except Exception:  # pragma: no cover
    Request = None  # type: ignore
    urlopen = None  # type: ignore
    HTTPError = Exception  # type: ignore
    URLError = Exception  # type: ignore


# ---- Constants (from spec) ----

WINDOW_START_ISO = "2025-10-29T18:00:00Z"
WINDOW_END_OPEN_ISO = "2025-10-30T05:59:00Z"  # open time of last included 1m candle

WINDOW_START_MS = 1761760800000
WINDOW_END_OPEN_MS = 1761803940000
INTERVAL_MS = 60_000
EXPECTED_FINAL_COUNT = 720

DEFAULT_BASE = "https://api.binance.com"
ALT_BASES = [
    "https://api-gcp.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]


def utc_now_ms() -> int:
    return int(time.time() * 1000)


def floor_to_minute_open_ms(ms: int) -> int:
    return ms - (ms % INTERVAL_MS)


def iso_now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_timestamp_for_dir() -> str:
    # Use ISO-like string with colon safe for most filesystems
    # Keep colon to match human-readable ISO; it's valid on POSIX/macOS.
    return iso_now_utc()


def sanitize_model_name(name: str) -> str:
    # keep alnum, dash, dot, underscore; replace spaces with dashes
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._")
    name = name.replace(" ", "-")
    return "".join(ch for ch in name if ch in allowed) or "model"


@dataclass
class FetchResult:
    endpoint: str
    status: int
    body: bytes


def http_get(url: str, timeout_s: float = 15.0, headers: Optional[Dict[str, str]] = None) -> FetchResult:
    req = Request(url, headers={
        "User-Agent": "metric-report-twap/1.0 (+https://binance.com)",
        **(headers or {}),
    })
    try:
        with urlopen(req, timeout=timeout_s) as resp:  # type: ignore[arg-type]
            body = resp.read()
            status = getattr(resp, "status", 200)
            endpoint = f"{resp.url}"  # type: ignore[attr-defined]
            return FetchResult(endpoint=endpoint, status=status, body=body)
    except HTTPError as e:  # type: ignore[misc]
        return FetchResult(endpoint=url, status=getattr(e, "code", 599), body=b"")
    except URLError:  # type: ignore[misc]
        return FetchResult(endpoint=url, status=598, body=b"")


def build_klines_url(base: str, symbol: str, start_ms: int, limit: int) -> str:
    return (
        f"{base.rstrip('/')}/api/v3/klines?symbol={symbol}&interval=1m&startTime={start_ms}&limit={limit}"
    )


def fetch_klines_with_retries(
    symbol: str,
    base: str,
    alt_bases: Sequence[str],
    start_ms: int,
    limit: int = EXPECTED_FINAL_COUNT,
    retries: int = 3,
    timeout_s: float = 15.0,
) -> Tuple[List[Any], str, Dict[str, Any]]:
    """
    Returns (klines_json, endpoint_used, request_params)
    On failure after retries, raises RuntimeError.
    """
    # rotation order per attempt
    bases = [base] + [b for b in alt_bases if b != base]
    last_err_status: Optional[int] = None
    last_endpoint = ""

    for attempt in range(retries):
        for b in bases:
            url = build_klines_url(b, symbol, start_ms, limit)
            res = http_get(url, timeout_s=timeout_s)
            last_endpoint = url
            if res.status == 200 and res.body:
                try:
                    data = json.loads(res.body.decode("utf-8"))
                    if isinstance(data, list):
                        return data, b, {
                            "symbol": symbol,
                            "interval": "1m",
                            "startTime": start_ms,
                            "limit": limit,
                        }
                except Exception:
                    # treat as parse failure; continue
                    last_err_status = 597
                    continue
            # 429/5xx/timeouts: backoff, try next base
            last_err_status = res.status
        time.sleep(0.4 * (attempt + 1))

    raise RuntimeError(f"Network failure after retries; last_status={last_err_status} endpoint={last_endpoint}")


def compute_effective_end_open_ms(now_ms: int) -> int:
    last_closed_open_ms = floor_to_minute_open_ms(now_ms) - INTERVAL_MS
    return min(WINDOW_END_OPEN_MS, last_closed_open_ms)


def post_filter_and_sort(
    klines: Sequence[Sequence[Any]], start_ms: int, effective_end_open_ms: int
) -> List[Sequence[Any]]:
    out = [
        k for k in klines
        if isinstance(k, (list, tuple))
        and len(k) >= 5
        and isinstance(k[0], (int, float))
        and int(k[0]) >= start_ms
        and int(k[0]) <= effective_end_open_ms
    ]
    out.sort(key=lambda k: int(k[0]))
    return out


def expected_count_for_now(effective_end_open_ms: int) -> int:
    if effective_end_open_ms < WINDOW_START_MS:
        return 0
    return int(((effective_end_open_ms - WINDOW_START_MS) // INTERVAL_MS) + 1)


def check_contiguity(
    observed_opens_ms: Sequence[int], effective_end_open_ms: int
) -> Tuple[bool, List[int]]:
    if not observed_opens_ms:
        return True, []
    expected_last = effective_end_open_ms
    expected_opens = list(range(WINDOW_START_MS, expected_last + 1, INTERVAL_MS))
    obs_set = set(int(x) for x in observed_opens_ms)
    missing = [t for t in expected_opens if t not in obs_set]
    contiguous = len(missing) == 0
    return contiguous, missing


def decimal_mean(values: Iterable[Decimal]) -> Optional[Decimal]:
    total = Decimal(0)
    n = 0
    for v in values:
        total += v
        n += 1
    if n == 0:
        return None
    return total / Decimal(n)


def round_half_up_to_int_times_100(x: Decimal) -> int:
    # Multiply by 100 then round half-up to integer
    scaled = (x * Decimal(100))
    return int(scaled.to_integral_value(rounding=ROUND_HALF_UP))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compute 12-hour TWAP (Binance spot 1m klines) for BTCUSDT or ETHUSDT.\n"
            "Outputs integer = ROUND_HALF_UP(mean*100). Writes diagnostics JSON and raw klines."
        )
    )
    parser.add_argument(
        "--symbol",
        required=True,
        choices=["BTCUSDT", "ETHUSDT"],
        help="Symbol to compute TWAP for (BTCUSDT or ETHUSDT).",
    )
    parser.add_argument(
        "--exchange-base",
        default=DEFAULT_BASE,
        help=f"Primary Binance API base (default: {DEFAULT_BASE}).",
    )
    parser.add_argument(
        "--out-json",
        default="twap_result.json",
        help="Path for diagnostics JSON (default: twap_result.json).",
    )
    parser.add_argument(
        "--raw-out",
        default="klines_raw.json",
        help="Path for raw klines JSON (default: klines_raw.json).",
    )
    parser.add_argument(
        "--strict-final",
        action="store_true",
        help="If set, final window must be contiguous; else exit code 2.",
    )
    parser.add_argument(
        "--model-name",
        default="gpt-5-high",
        help="Model name for run directory naming (default: gpt-5-high).",
    )
    parser.add_argument(
        "--output-base-dir",
        default=None,
        help=(
            "Base directory where the timestamped run folder is created. "
            "Default: this package directory (2025-10-gpt-5-high)."
        ),
    )
    parser.add_argument(
        "--no-run-dir",
        action="store_true",
        help="Do not create the timestamped run directory; write outputs to CWD or given paths.",
    )

    args = parser.parse_args(argv)

    # Decimal precision ample for averaging 720 prices with 2 decimal rounding
    getcontext().prec = 40

    # Compute effective end boundary based on current time
    now_ms = utc_now_ms()
    now_iso = iso_now_utc()
    effective_end_open = compute_effective_end_open_ms(now_ms)
    expected_count_now = expected_count_for_now(effective_end_open)

    # Prepare run directory
    run_dir: Optional[Path] = None
    model_sanitized = sanitize_model_name(args.model_name)
    if not args.no_run_dir:
        if args.output_base_dir is not None:
            base_dir = Path(args.output_base_dir).expanduser().resolve()
        else:
            # Default base is the package directory (../ from this script)
            base_dir = Path(__file__).resolve().parents[1]
        timestamp_str = iso_timestamp_for_dir()
        run_dir = base_dir / f"{timestamp_str}-{model_sanitized}"
        run_dir.mkdir(parents=True, exist_ok=True)

    # Resolve output files (place inside run_dir if using defaults)
    out_json_path = Path(args.out_json)
    raw_out_path = Path(args.raw_out)
    if run_dir is not None:
        if args.out_json == "twap_result.json":
            out_json_path = run_dir / args.out_json
        if args.raw_out == "klines_raw.json":
            raw_out_path = run_dir / args.raw_out

    # Fetch klines if window already started; else zero-observed
    observed: List[Sequence[Any]] = []
    endpoint_used = ""
    request_params: Dict[str, Any] = {
        "symbol": args.symbol,
        "interval": "1m",
        "startTime": WINDOW_START_MS,
        "limit": EXPECTED_FINAL_COUNT,
    }

    if effective_end_open >= WINDOW_START_MS:
        try:
            klines, base_used, reqp = fetch_klines_with_retries(
                symbol=args.symbol,
                base=args.exchange_base,
                alt_bases=ALT_BASES,
                start_ms=WINDOW_START_MS,
                limit=EXPECTED_FINAL_COUNT,
            )
            endpoint_used = base_used
            request_params = reqp
            # write raw as returned
            if raw_out_path:
                Path(raw_out_path).write_text(json.dumps(klines, indent=2) + "\n", encoding="utf-8")

            observed = post_filter_and_sort(klines, WINDOW_START_MS, effective_end_open)

            # If short vs expected for now, retry a few times quickly
            retry_budget = 2
            while len(observed) < expected_count_now and retry_budget > 0:
                time.sleep(0.3)
                klines, base_used, reqp = fetch_klines_with_retries(
                    symbol=args.symbol,
                    base=args.exchange_base,
                    alt_bases=ALT_BASES,
                    start_ms=WINDOW_START_MS,
                    limit=EXPECTED_FINAL_COUNT,
                )
                endpoint_used = base_used
                request_params = reqp
                observed = post_filter_and_sort(klines, WINDOW_START_MS, effective_end_open)
                retry_budget -= 1
        except Exception as e:
            # network failure
            print("null")
            print(f"error: network failure after retries ({e})")
            # write diagnostics json with error
            diag = {
                "symbol": args.symbol,
                "interval": "1m",
                "window_start_iso": WINDOW_START_ISO,
                "window_end_open_iso": WINDOW_END_OPEN_ISO,
                "now_iso": now_iso,
                "effective_end_open_iso": datetime.fromtimestamp(effective_end_open/1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "observed_count": 0,
                "expected_count_for_now": expected_count_now,
                "complete": False,
                "contiguous": True,
                "missing_open_times_ms": [],
                "twap_mean": None,
                "result_integer_times_100": None,
                "notes": "error",
                "source": {
                    "endpoint": endpoint_used or args.exchange_base,
                    "request_params": request_params,
                },
            }
            write_json(Path(out_json_path), diag)
            return 3

    observed_count = len(observed)
    observed_opens = [int(k[0]) for k in observed]
    contiguous, missing = check_contiguity(observed_opens, effective_end_open)

    closes: List[Decimal] = []
    for k in observed:
        try:
            closes.append(Decimal(str(k[4])))
        except Exception:
            # skip malformed
            pass

    mean_dec = decimal_mean(closes)
    if mean_dec is None:
        result_int_times_100: Optional[int] = None
    else:
        result_int_times_100 = round_half_up_to_int_times_100(mean_dec)

    complete = (
        observed_count == EXPECTED_FINAL_COUNT and effective_end_open == WINDOW_END_OPEN_MS
    )

    # stdout per spec
    if result_int_times_100 is None:
        print("null")
        print("status: no-data-yet" if expected_count_now == 0 else "status: temporary-no-mean")
    else:
        if complete and contiguous:
            print(str(result_int_times_100))
        else:
            print(str(result_int_times_100))
            status = "temporary"
            if complete and not contiguous:
                status = "final-noncontiguous"
            print(
                f"status: {status}; observed={observed_count} expected_now={expected_count_now} contiguous={str(contiguous).lower()}"
            )

    # diagnostics JSON
    diag = {
        "symbol": args.symbol,
        "interval": "1m",
        "window_start_iso": WINDOW_START_ISO,
        "window_end_open_iso": WINDOW_END_OPEN_ISO,
        "now_iso": now_iso,
        "effective_end_open_iso": datetime.fromtimestamp(
            effective_end_open / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observed_count": observed_count,
        "expected_count_for_now": expected_count_now,
        "complete": bool(complete),
        "contiguous": bool(contiguous),
        "missing_open_times_ms": missing,
        "twap_mean": None if mean_dec is None else str(mean_dec),
        "result_integer_times_100": result_int_times_100,
        "notes": ("final" if complete and contiguous else ("temporary" if observed_count > 0 else "early")),
        "source": {
            "endpoint": endpoint_used or args.exchange_base,
            "request_params": request_params,
        },
    }
    write_json(Path(out_json_path), diag)

    # Per spec: final window but non-contiguous → exit 2
    if complete and not contiguous:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
