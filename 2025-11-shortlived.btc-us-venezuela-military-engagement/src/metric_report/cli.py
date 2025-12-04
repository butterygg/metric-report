from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, getcontext
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

getcontext().prec = 50

CMC_ENDPOINT = "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/detail/chart"
TIMESTAMP_MS_THRESHOLD = 10_000_000_000
WINDOW_OFFSET_SECONDS = 43_200
WINDOW_LENGTH_SECONDS = 43_200


class MetricError(Exception):
    """Raised when the metric cannot be computed."""


@dataclass(frozen=True)
class QuestionConfig:
    question_id: str
    asset_id: int
    convert_id: int
    min_decision_epoch: int
    market_end_epoch: int
    require_decision_input: bool
    default_decision_epoch: int | None


CONFIG = QuestionConfig(
    question_id="btc-us-venezuela-military-engagement",
    asset_id=1,
    convert_id=2781,
    min_decision_epoch=1762473600,
    market_end_epoch=1763078400,
    require_decision_input=False,
    default_decision_epoch=1763078400,
)


def build_parser(config: QuestionConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute the BTC/USD Reality metric by sampling CoinMarketCap detail/chart "
            "prices 12–24 hours after the market cutoff (or an optional override)."
        )
    )
    parser.add_argument(
        "--decision-time",
        help=(
            "ISO8601 timestamp for a qualifying engagement report. Defaults to the market "
            "cutoff when omitted."
        ),
    )
    parser.add_argument(
        "--decision-time-epoch",
        type=int,
        help="Unix timestamp seconds for the engagement decision (alternative to --decision-time).",
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        help="Optional directory where diagnostics such as result.json will be written.",
    )
    parser.add_argument(
        "--raw-points",
        type=Path,
        help="Optional path to dump the raw CoinMarketCap response JSON.",
    )
    parser.add_argument(
        "--stdout-json",
        action="store_true",
        help="When set, emit the diagnostics JSON to stdout instead of only the integer.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="How many times to retry the CoinMarketCap request (default: 3).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds for the CoinMarketCap request (default: 30).",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=1.5,
        help="Multiplier for exponential backoff between retries (default: 1.5).",
    )
    parser.set_defaults(config=config)
    return parser


def iso_to_epoch_seconds(value: str) -> int:
    text = value.strip()
    text = text[:-1] + "+00:00" if text.endswith("Z") else text
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def epoch_to_iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_decision_epoch(args: argparse.Namespace, config: QuestionConfig) -> int:
    epoch_from_iso = iso_to_epoch_seconds(args.decision_time) if args.decision_time else None
    epoch_direct = args.decision_time_epoch

    if epoch_from_iso is not None and epoch_direct is not None and epoch_from_iso != epoch_direct:
        raise MetricError("--decision-time and --decision-time-epoch disagree.")

    epoch = epoch_from_iso if epoch_from_iso is not None else epoch_direct

    if epoch is None:
        if config.require_decision_input:
            raise MetricError("Decision time is required for this metric.")
        if config.default_decision_epoch is None:
            raise MetricError("No default decision time is configured.")
        epoch = config.default_decision_epoch

    if epoch < config.min_decision_epoch:
        raise MetricError("Decision time predates the allowed market window.")

    if epoch > config.market_end_epoch:
        if config.require_decision_input:
            raise MetricError("Decision time must be on or before the market end.")
        epoch = config.market_end_epoch

    return epoch


def compute_window(decision_epoch: int) -> tuple[int, int]:
    start = decision_epoch + WINDOW_OFFSET_SECONDS
    end = start + WINDOW_LENGTH_SECONDS
    return start, end


def build_request_url(config: QuestionConfig, start: int, end: int) -> str:
    return (
        f"{CMC_ENDPOINT}?id={config.asset_id}&convertId={config.convert_id}"
        f"&range={start}~{end}"
    )


def fetch_payload(url: str, timeout: int, retries: int, backoff: float) -> Dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "cfm-metric-cli/0.1"})
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError) as exc:  # pragma: no cover - network
            last_error = exc
            if attempt == retries:
                raise MetricError(f"Failed to fetch CoinMarketCap data: {exc}") from exc
            time.sleep(backoff * attempt)
    raise MetricError(f"Failed to fetch CoinMarketCap data: {last_error}")


def normalize_timestamp(raw_ts: Any) -> int | None:
    value: float | int | None
    if isinstance(raw_ts, (int, float)):
        value = raw_ts
    elif isinstance(raw_ts, str):
        raw = raw_ts.strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
    else:
        return None
    ts = int(value)
    if ts > TIMESTAMP_MS_THRESHOLD:
        ts //= 1000
    return ts


def extract_price(sample: Any) -> Decimal | None:
    candidate: Any
    if isinstance(sample, dict):
        vec = sample.get("v")
        if isinstance(vec, list) and vec:
            candidate = vec[0]
        else:
            candidate = sample.get("c")
    elif isinstance(sample, list) and sample:
        candidate = sample[0]
    else:
        candidate = None
    if candidate is None:
        return None
    try:
        dec = Decimal(str(candidate))
    except (InvalidOperation, ValueError):
        return None
    if dec <= 0:
        return None
    return dec


def collect_window_prices(payload: Dict[str, Any], start: int, end: int) -> tuple[List[Decimal], Dict[str, Any] | None]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MetricError("Unexpected payload format: missing data field.")
    points = data.get("points")
    if not isinstance(points, dict):
        raise MetricError("Unexpected payload format: missing data.points field.")

    latest_price_by_ts: Dict[int, Decimal] = {}
    for raw_ts, sample in points.items():
        ts = normalize_timestamp(raw_ts)
        if ts is None or not (start <= ts < end):
            continue
        price = extract_price(sample)
        if price is None:
            continue
        latest_price_by_ts[ts] = price

    ordered_items = sorted(latest_price_by_ts.items(), key=lambda item: item[0])
    prices = [price for _, price in ordered_items]

    if not prices:
        return [], None

    range_info = {
        "earliest_epoch": ordered_items[0][0],
        "earliest_iso": epoch_to_iso(ordered_items[0][0]),
        "latest_epoch": ordered_items[-1][0],
        "latest_iso": epoch_to_iso(ordered_items[-1][0]),
    }
    return prices, range_info


def median_price(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise MetricError("No price samples available inside the TWAP window.")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / Decimal(2)


def ceil_cents(value: Decimal) -> int:
    cents = value * Decimal(100)
    return int(cents.to_integral_value(rounding=ROUND_CEILING))


def write_artifacts(artifacts_dir: Path | None, diagnostics: Dict[str, Any]) -> None:
    if artifacts_dir is None:
        return
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifacts_dir / "result.json"
    result_path.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")


def dump_raw_points(raw_path: Path | None, payload: Dict[str, Any]) -> None:
    if raw_path is None:
        return
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_metric(args: argparse.Namespace) -> Dict[str, Any]:
    config: QuestionConfig = args.config
    decision_source = (
        "operator-input"
        if args.decision_time is not None or args.decision_time_epoch is not None
        else "default-market-end"
    )
    decision_epoch = resolve_decision_epoch(args, config)
    window_start, window_end = compute_window(decision_epoch)
    request_url = build_request_url(config, window_start, window_end)
    payload = fetch_payload(request_url, timeout=args.timeout, retries=args.retries, backoff=args.backoff)
    dump_raw_points(args.raw_points, payload)
    prices, observed_range = collect_window_prices(payload, window_start, window_end)
    if not prices:
        raise MetricError("CoinMarketCap response did not contain any usable samples.")
    med = median_price(prices)
    result_int = ceil_cents(med)

    diagnostics: Dict[str, Any] = {
        "question": config.question_id,
        "asset_id": config.asset_id,
        "convert_id": config.convert_id,
        "decision_time_epoch": decision_epoch,
        "decision_time_iso": epoch_to_iso(decision_epoch),
        "window_start_epoch": window_start,
        "window_start_iso": epoch_to_iso(window_start),
        "window_end_epoch": window_end,
        "window_end_iso": epoch_to_iso(window_end),
        "observed_count": len(prices),
        "median_price": str(med),
        "result_integer_times_100": result_int,
        "request_url": request_url,
        "decision_source": decision_source,
    }
    if observed_range is not None:
        diagnostics["observed_range"] = observed_range

    write_artifacts(args.artifacts, diagnostics)
    return diagnostics


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(CONFIG)
    args = parser.parse_args(argv)
    try:
        diagnostics = run_metric(args)
    except MetricError as exc:
        print("null")
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.stdout_json:
        print(json.dumps(diagnostics, indent=2))
    else:
        print(diagnostics["result_integer_times_100"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
