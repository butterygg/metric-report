from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import httpx

from .core import (
    ALLOWED_SYMBOLS,
    EXPECTED_FINAL_COUNT,
    WINDOW_END_OPEN_ISO,
    WINDOW_END_OPEN_MS,
    WINDOW_START_ISO,
    WINDOW_START_MS,
    ProcessedData,
    process,
)
from .fetch import DEFAULT_BASE_URLS, FetchError, fetch_klines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="binance-twap",
        description=(
            "Compute the 12-hour TWAP (1m interval) for Binance spot BTCUSDT or ETHUSDT "
            "over the 2025-10-29 18:00:00Z to 2025-10-30 05:59:00Z window."
        ),
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="Spot symbol to query (BTCUSDT or ETHUSDT).",
    )
    parser.add_argument(
        "--start",
        default=WINDOW_START_ISO,
        help=f"ISO8601 inclusive start time (default: {WINDOW_START_ISO}).",
    )
    parser.add_argument(
        "--end-open",
        default=WINDOW_END_OPEN_ISO,
        help=f"ISO8601 open time of last included minute (default: {WINDOW_END_OPEN_ISO}).",
    )
    parser.add_argument(
        "--exchange-base",
        action="append",
        default=None,
        help=(
            "Base URL for Binance API. May be provided multiple times to specify fallbacks. "
            f"Defaults to: {', '.join(DEFAULT_BASE_URLS)}."
        ),
    )
    parser.add_argument(
        "--out-json",
        default="twap_result.json",
        help="Path to write JSON diagnostics (default: ./twap_result.json).",
    )
    parser.add_argument(
        "--raw-out",
        default="klines_raw.json",
        help="Path to write raw klines payload (default: ./klines_raw.json).",
    )
    parser.add_argument(
        "--strict-final",
        action="store_true",
        help="Exit with code 2 unless the final result has 720 contiguous minutes.",
    )
    return parser


def _validate_fixed_window(start: str, end_open: str) -> None:
    if start != WINDOW_START_ISO or end_open != WINDOW_END_OPEN_ISO:
        raise SystemExit(
            "error: --start and --end-open must match the canonical window "
            f"({WINDOW_START_ISO} -> {WINDOW_END_OPEN_ISO})."
        )


def _resolve_base_urls(value: Sequence[str] | None) -> list[str]:
    if value is None:
        return list(DEFAULT_BASE_URLS)
    resolved = [url.rstrip("/") for url in value]
    return resolved or list(DEFAULT_BASE_URLS)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _write_raw(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.write("\n")


def _emit_stdout(result: ProcessedData) -> None:
    metrics = result.metrics
    if metrics.complete and metrics.contiguous and result.exit_code == 0:
        assert metrics.result_integer_times_100 is not None
        print(metrics.result_integer_times_100)
        return
    value = (
        str(metrics.result_integer_times_100)
        if metrics.result_integer_times_100 is not None
        else "null"
    )
    print(value)
    print(f"status: {metrics.notes}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    _validate_fixed_window(args.start, args.end_open)

    symbol = args.symbol.upper()
    if symbol not in ALLOWED_SYMBOLS:
        raise SystemExit(f"error: symbol must be one of {sorted(ALLOWED_SYMBOLS)}.")

    base_urls = _resolve_base_urls(args.exchange_base)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    endpoint = base_urls[0]
    raw_klines: list[list[object]] = []

    if now_ms >= WINDOW_START_MS:
        try:
            with httpx.Client() as client:
                outcome = fetch_klines(
                    symbol,
                    client=client,
                    base_urls=base_urls,
                    start_time_ms=WINDOW_START_MS,
                    limit=EXPECTED_FINAL_COUNT,
                )
            endpoint = outcome.endpoint
            raw_klines = outcome.klines
        except FetchError as exc:
            print("null")
            print(f"status: error ({exc})")
            return 3

    processed = process(
        symbol,
        raw_klines,
        now_ms,
        endpoint,
        strict_final=args.strict_final,
    )

    diagnostics_path = Path(args.out_json)
    raw_path = Path(args.raw_out)
    _write_json(diagnostics_path, processed.diagnostics)
    _write_raw(raw_path, processed.raw_klines)

    _emit_stdout(processed)

    return processed.exit_code


if __name__ == "__main__":
    sys.exit(main())
