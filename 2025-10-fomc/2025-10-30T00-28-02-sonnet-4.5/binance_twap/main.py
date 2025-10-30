#!/usr/bin/env python3
"""
Binance TWAP Calculator

Computes the 12-hour TWAP of Binance spot prices (BTCUSDT or ETHUSDT) using 1-minute klines.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import requests

# Constants from spec
WINDOW_START_ISO = "2025-10-29T18:00:00Z"
WINDOW_END_OPEN_ISO = "2025-10-30T05:59:00Z"
WINDOW_START_MS = 1761760800000
WINDOW_END_OPEN_MS = 1761803940000
INTERVAL_MS = 60000
EXPECTED_FINAL_COUNT = 720
ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT"}
DEFAULT_EXCHANGE_BASE = "https://api.binance.com"
FALLBACK_EXCHANGES = [
    "https://api-gcp.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="""
Compute the 12-hour TWAP of a Binance spot symbol.

This tool calculates the Time-Weighted Average Price (TWAP) as the simple average
of exactly 720 one-minute close prices from Binance 1m klines, covering the UTC window:
  • Start (inclusive): 2025-10-29 18:00:00 UTC
  • End (inclusive):   2025-10-30 05:59:00 UTC

The result is multiplied by 100 and rounded half-up to the nearest integer.

If the window hasn't finished yet, a temporary TWAP is computed from the available
fully-closed 1-minute candles.

OUTPUT:
  • Final (complete): Prints only the result integer on the first line
  • Temporary/error:  Prints the result or 'null', then a status line
  • JSON diagnostics: Written to --out-json (default: ./twap_result.json)
  • Raw klines:       Written to --raw-out (default: ./klines_raw.json)

EXIT CODES:
  0 = Success (temporary or final)
  2 = Final run but not exactly 720 contiguous minutes
  3 = Network failure after retries

EXAMPLES:
  %(prog)s --symbol BTCUSDT
  %(prog)s --symbol ETHUSDT --out-json eth_result.json
  %(prog)s --symbol BTCUSDT --strict-final
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        choices=list(ALLOWED_SYMBOLS),
        help="Binance spot symbol (BTCUSDT or ETHUSDT)",
    )

    parser.add_argument(
        "--start",
        type=str,
        default=WINDOW_START_ISO,
        help=f"Window start ISO timestamp (default: {WINDOW_START_ISO})",
    )

    parser.add_argument(
        "--end-open",
        type=str,
        default=WINDOW_END_OPEN_ISO,
        help=f"Window end ISO timestamp - open time of last candle (default: {WINDOW_END_OPEN_ISO})",
    )

    parser.add_argument(
        "--exchange-base",
        type=str,
        default=DEFAULT_EXCHANGE_BASE,
        help=f"Binance API base URL (default: {DEFAULT_EXCHANGE_BASE})",
    )

    parser.add_argument(
        "--out-json",
        type=str,
        default="./twap_result.json",
        help="Path for JSON diagnostics output (default: ./twap_result.json)",
    )

    parser.add_argument(
        "--raw-out",
        type=str,
        default="./klines_raw.json",
        help="Path for raw klines output (default: ./klines_raw.json)",
    )

    parser.add_argument(
        "--strict-final",
        action="store_true",
        help="Exit with code 2 if final run doesn't have exactly 720 contiguous minutes",
    )

    return parser.parse_args()


def get_now_utc_ms() -> int:
    """Get current UTC time in milliseconds."""
    return int(time.time() * 1000)


def floor_to_minute_ms(timestamp_ms: int) -> int:
    """Floor timestamp to the start of its minute."""
    return (timestamp_ms // INTERVAL_MS) * INTERVAL_MS


def fetch_klines(
    symbol: str,
    start_time_ms: int,
    limit: int,
    exchange_base: str,
) -> list[list[Any]]:
    """
    Fetch klines from Binance API with retry logic and fallback exchanges.

    Args:
        symbol: Trading pair symbol
        start_time_ms: Start time in milliseconds
        limit: Number of candles to fetch
        exchange_base: Base URL for Binance API

    Returns:
        List of kline arrays

    Raises:
        RuntimeError: If all retries and fallbacks fail
    """
    exchanges = [exchange_base] + FALLBACK_EXCHANGES
    params = {
        "symbol": symbol,
        "interval": "1m",
        "startTime": start_time_ms,
        "limit": limit,
    }

    for exchange in exchanges:
        url = f"{exchange}/api/v3/klines"

        for attempt in range(3):
            try:
                response = requests.get(url, params=params, timeout=10)

                if response.status_code == 200:
                    return response.json()  # type: ignore[no-any-return]

                if response.status_code == 429:
                    # Rate limited, try next exchange
                    print(
                        f"Rate limited on {exchange}, attempt {attempt + 1}/3",
                        file=sys.stderr,
                    )
                    time.sleep(1 * (attempt + 1))
                    continue

                if response.status_code >= 500:
                    print(
                        f"Server error {response.status_code} on {exchange}, "
                        f"attempt {attempt + 1}/3",
                        file=sys.stderr,
                    )
                    time.sleep(1 * (attempt + 1))
                    continue

                # Other error, try next exchange
                print(
                    f"HTTP {response.status_code} on {exchange}: {response.text[:100]}",
                    file=sys.stderr,
                )
                break

            except (requests.RequestException, requests.Timeout) as e:
                print(
                    f"Network error on {exchange}, attempt {attempt + 1}/3: {e}",
                    file=sys.stderr,
                )
                time.sleep(1 * (attempt + 1))

    raise RuntimeError("Failed to fetch klines after all retries and fallback exchanges")


def validate_and_filter_klines(
    klines: list[list[Any]],
    symbol: str,
    effective_end_open_ms: int,
) -> list[dict[str, Any]]:
    """
    Validate and filter klines to the effective window.

    Args:
        klines: Raw kline data from Binance
        symbol: Expected symbol
        effective_end_open_ms: Maximum open time to include

    Returns:
        List of validated and filtered klines as dictionaries
    """
    filtered = []

    for k in klines:
        open_time = int(k[0])

        if open_time > effective_end_open_ms:
            continue

        # Parse kline data
        kline_dict = {
            "openTime": open_time,
            "open": str(k[1]),
            "high": str(k[2]),
            "low": str(k[3]),
            "close": str(k[4]),  # Index 4 is close price
            "volume": str(k[5]),
            "closeTime": int(k[6]),
            "quoteVolume": str(k[7]),
            "trades": int(k[8]),
            "takerBuyBaseVolume": str(k[9]),
            "takerBuyQuoteVolume": str(k[10]),
            "ignore": str(k[11]),
        }

        filtered.append(kline_dict)

    return filtered


def check_contiguity(
    klines: list[dict[str, Any]],
    start_ms: int,
) -> tuple[bool, list[int]]:
    """
    Check if klines are contiguous starting from start_ms.

    Args:
        klines: List of kline dictionaries
        start_ms: Expected start time

    Returns:
        Tuple of (is_contiguous, list_of_missing_open_times)
    """
    if not klines:
        return True, []

    expected_times = {start_ms + i * INTERVAL_MS for i in range(len(klines))}
    actual_times = {k["openTime"] for k in klines}
    missing = sorted(expected_times - actual_times)

    # Also check ordering
    for i, k in enumerate(klines):
        expected = start_ms + i * INTERVAL_MS
        if k["openTime"] != expected:
            return False, missing

    return len(missing) == 0, missing


def calculate_twap(klines: list[dict[str, Any]]) -> tuple[Decimal | None, int | None]:
    """
    Calculate TWAP from klines using decimal arithmetic.

    Args:
        klines: List of kline dictionaries

    Returns:
        Tuple of (mean_decimal, result_integer_times_100)
    """
    if not klines:
        return None, None

    closes = [Decimal(k["close"]) for k in klines]
    mean = sum(closes) / Decimal(len(closes))

    # Multiply by 100 and round half-up
    result_times_100 = (mean * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    return mean, int(result_times_100)


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Get current time and calculate effective end
    now_ms = get_now_utc_ms()
    last_closed_minute_open_ms = floor_to_minute_ms(now_ms) - INTERVAL_MS
    effective_end_open_ms = min(WINDOW_END_OPEN_MS, last_closed_minute_open_ms)

    # Calculate expected count
    if effective_end_open_ms < WINDOW_START_MS:
        expected_partial_count = 0
    else:
        expected_partial_count = ((effective_end_open_ms - WINDOW_START_MS) // INTERVAL_MS) + 1

    # Fetch klines
    try:
        raw_klines = fetch_klines(
            symbol=args.symbol,
            start_time_ms=WINDOW_START_MS,
            limit=EXPECTED_FINAL_COUNT,
            exchange_base=args.exchange_base,
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(3)

    # Save raw klines
    Path(args.raw_out).write_text(json.dumps(raw_klines, indent=2))

    # Validate and filter
    filtered_klines = validate_and_filter_klines(
        raw_klines,
        args.symbol,
        effective_end_open_ms,
    )

    # Sort by open time
    filtered_klines.sort(key=lambda k: k["openTime"])

    # Check contiguity
    contiguous, missing_times = check_contiguity(filtered_klines, WINDOW_START_MS)

    # Calculate TWAP
    mean, result = calculate_twap(filtered_klines)

    # Determine completeness
    observed_count = len(filtered_klines)
    complete = (
        observed_count == EXPECTED_FINAL_COUNT and effective_end_open_ms == WINDOW_END_OPEN_MS
    )

    # Prepare diagnostics
    diagnostics = {
        "symbol": args.symbol,
        "interval": "1m",
        "window_start_iso": WINDOW_START_ISO,
        "window_end_open_iso": WINDOW_END_OPEN_ISO,
        "now_iso": datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).isoformat(),
        "effective_end_open_iso": datetime.fromtimestamp(
            effective_end_open_ms / 1000,
            tz=timezone.utc,
        ).isoformat(),
        "observed_count": observed_count,
        "expected_count_for_now": int(expected_partial_count),
        "complete": complete,
        "contiguous": contiguous,
        "missing_open_times_ms": missing_times,
        "twap_mean": str(mean) if mean is not None else None,
        "result_integer_times_100": result,
        "notes": "final" if complete else ("temporary" if result is not None else "error"),
        "source": {
            "endpoint": args.exchange_base,
            "request_params": {
                "symbol": args.symbol,
                "interval": "1m",
                "startTime": WINDOW_START_MS,
                "limit": EXPECTED_FINAL_COUNT,
            },
        },
    }

    # Write diagnostics JSON
    Path(args.out_json).write_text(json.dumps(diagnostics, indent=2))

    # Output to stdout
    if complete and contiguous:
        # Final success - print only the result
        print(result)
    elif complete and not contiguous:
        # Final but not contiguous
        print(f"{result if result is not None else 'null'}")
        print(f"ERROR: Final run but not contiguous (missing {len(missing_times)} candles)")
        if args.strict_final:
            sys.exit(2)
    else:
        # Temporary or error
        print(f"{result if result is not None else 'null'}")
        status = (
            f"Temporary TWAP: {observed_count}/{int(expected_partial_count)} candles "
            f"({'contiguous' if contiguous else 'gaps detected'})"
        )
        print(status)

    # Exit code
    if complete and not contiguous:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
