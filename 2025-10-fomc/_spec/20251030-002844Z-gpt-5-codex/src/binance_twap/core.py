from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Iterable, Sequence

INTERVAL_MS = 60_000
EXPECTED_FINAL_COUNT = 720
WINDOW_START_MS = 1_761_760_800_000
WINDOW_END_OPEN_MS = 1_761_803_940_000
WINDOW_START_ISO = "2025-10-29T18:00:00Z"
WINDOW_END_OPEN_ISO = "2025-10-30T05:59:00Z"
ALLOWED_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT"})

getcontext().prec = 34


@dataclass(frozen=True)
class Metrics:
    result_integer_times_100: int | None
    twap_mean: Decimal | None
    observed_count: int
    expected_count_for_now: int
    complete: bool
    contiguous: bool
    missing_open_times_ms: list[int]
    effective_end_open_ms: int
    notes: str


@dataclass(frozen=True)
class ProcessedData:
    metrics: Metrics
    diagnostics: dict[str, Any]
    raw_klines: list[list[Any]]
    exit_code: int


def floor_to_minute(open_ms: int) -> int:
    return open_ms - (open_ms % INTERVAL_MS)


def compute_effective_end_open_ms(now_ms: int) -> int:
    last_closed_open_ms = floor_to_minute(now_ms) - INTERVAL_MS
    return min(WINDOW_END_OPEN_MS, last_closed_open_ms)


def isoformat_from_ms(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def expected_count_for_effective_end(effective_end_open_ms: int) -> int:
    if effective_end_open_ms < WINDOW_START_MS:
        return 0
    delta = effective_end_open_ms - WINDOW_START_MS
    return int(delta / INTERVAL_MS) + 1


def parse_close(value: Any) -> Decimal:
    if isinstance(value, (float, int)):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise TypeError(f"Unsupported close value type: {type(value)}")


def normalise_kline(kline: Sequence[Any]) -> tuple[int, Decimal]:
    open_time = int(kline[0])
    close_price = parse_close(kline[4])
    return open_time, close_price


def collect_observed_klines(
    raw_klines: Iterable[Sequence[Any]],
    effective_end_open_ms: int,
) -> list[tuple[int, Decimal]]:
    observed: list[tuple[int, Decimal]] = []
    for kline in raw_klines:
        open_time, close_price = normalise_kline(kline)
        if open_time < WINDOW_START_MS:
            continue
        if open_time > effective_end_open_ms:
            continue
        observed.append((open_time, close_price))
    observed.sort(key=lambda item: item[0])
    return observed


def compute_missing_open_times(
    observed_open_times: list[int],
    effective_end_open_ms: int,
) -> list[int]:
    if not observed_open_times:
        return [
            ts
            for ts in range(WINDOW_START_MS, effective_end_open_ms + 1, INTERVAL_MS)
        ]
    observed_set = set(observed_open_times)
    return [
        ts
        for ts in range(WINDOW_START_MS, effective_end_open_ms + 1, INTERVAL_MS)
        if ts not in observed_set
    ]


def round_half_up_to_int(value: Decimal) -> int:
    scaled = (value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    result = int(scaled)
    if result < 0:
        raise ValueError("TWAP result must be unsigned.")
    return result


def build_diagnostics(
    symbol: str,
    now_ms: int,
    effective_end_open_ms: int,
    metrics: Metrics,
    endpoint: str,
) -> dict[str, Any]:
    twap_mean_str = str(metrics.twap_mean) if metrics.twap_mean is not None else None
    result_val: int | None = metrics.result_integer_times_100
    now_iso = isoformat_from_ms(now_ms)
    effective_end_iso = (
        isoformat_from_ms(metrics.effective_end_open_ms)
        if metrics.effective_end_open_ms >= WINDOW_START_MS
        else None
    )
    return {
        "symbol": symbol,
        "interval": "1m",
        "window_start_iso": WINDOW_START_ISO,
        "window_end_open_iso": WINDOW_END_OPEN_ISO,
        "now_iso": now_iso,
        "effective_end_open_iso": effective_end_iso,
        "observed_count": metrics.observed_count,
        "expected_count_for_now": metrics.expected_count_for_now,
        "complete": metrics.complete,
        "contiguous": metrics.contiguous,
        "missing_open_times_ms": metrics.missing_open_times_ms,
        "twap_mean": twap_mean_str,
        "result_integer_times_100": result_val,
        "notes": metrics.notes,
        "source": {
            "endpoint": endpoint,
            "request_params": {
                "symbol": symbol,
                "interval": "1m",
                "startTime": WINDOW_START_MS,
                "limit": EXPECTED_FINAL_COUNT,
            },
        },
    }


def process(
    symbol: str,
    raw_klines: list[list[Any]],
    now_ms: int,
    endpoint: str,
    *,
    strict_final: bool,
) -> ProcessedData:
    effective_end_open_ms = compute_effective_end_open_ms(now_ms)
    expected_count = expected_count_for_effective_end(effective_end_open_ms)

    if effective_end_open_ms < WINDOW_START_MS:
        metrics = Metrics(
            result_integer_times_100=None,
            twap_mean=None,
            observed_count=0,
            expected_count_for_now=0,
            complete=False,
            contiguous=True,
            missing_open_times_ms=[],
            effective_end_open_ms=effective_end_open_ms,
            notes="temporary",
        )
        diagnostics = build_diagnostics(symbol, now_ms, effective_end_open_ms, metrics, endpoint)
        return ProcessedData(metrics=metrics, diagnostics=diagnostics, raw_klines=raw_klines, exit_code=0)

    observed = collect_observed_klines(raw_klines, effective_end_open_ms)
    observed_open_times = [item[0] for item in observed]
    missing = compute_missing_open_times(observed_open_times, effective_end_open_ms)
    contiguous = not missing and len(observed) == expected_count
    complete = (
        effective_end_open_ms == WINDOW_END_OPEN_MS
        and len(observed) == EXPECTED_FINAL_COUNT
    )

    if not observed:
        metrics = Metrics(
            result_integer_times_100=None,
            twap_mean=None,
            observed_count=0,
            expected_count_for_now=expected_count,
            complete=complete,
            contiguous=contiguous,
            missing_open_times_ms=missing,
            effective_end_open_ms=effective_end_open_ms,
            notes="temporary" if not complete else "error",
        )
        diagnostics = build_diagnostics(symbol, now_ms, effective_end_open_ms, metrics, endpoint)
        exit_code = 2 if strict_final and complete else 0
        return ProcessedData(
            metrics=metrics,
            diagnostics=diagnostics,
            raw_klines=raw_klines,
            exit_code=exit_code,
        )

    closes = [close for _, close in observed]
    twap_mean = sum(closes, start=Decimal()) / Decimal(len(closes))
    result_value = round_half_up_to_int(twap_mean)

    notes = "final" if complete and contiguous else "temporary"
    exit_code = 0

    if complete and not contiguous:
        notes = "error"
        exit_code = 2
    elif strict_final and not (complete and contiguous):
        notes = "error"
        exit_code = 2

    metrics = Metrics(
        result_integer_times_100=result_value,
        twap_mean=twap_mean,
        observed_count=len(observed),
        expected_count_for_now=expected_count,
        complete=complete,
        contiguous=contiguous,
        missing_open_times_ms=missing,
        effective_end_open_ms=effective_end_open_ms,
        notes=notes,
    )

    diagnostics = build_diagnostics(symbol, now_ms, effective_end_open_ms, metrics, endpoint)

    return ProcessedData(
        metrics=metrics,
        diagnostics=diagnostics,
        raw_klines=raw_klines,
        exit_code=exit_code,
    )
