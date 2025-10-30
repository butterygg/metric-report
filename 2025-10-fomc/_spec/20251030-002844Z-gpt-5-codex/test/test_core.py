from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from binance_twap.core import (
    INTERVAL_MS,
    EXPECTED_FINAL_COUNT,
    WINDOW_END_OPEN_MS,
    WINDOW_START_MS,
    process,
)
from binance_twap.fetch import FetchError, fetch_klines


def _make_kline(open_time: int, close: str) -> list[object]:
    close_time = open_time + INTERVAL_MS - 1
    return [
        open_time,
        "0",
        "0",
        "0",
        close,
        "0",
        close_time,
        "0",
        0,
        "0",
        "0",
        "0",
    ]


def test_process_partial_window() -> None:
    now_ms = WINDOW_START_MS + 3 * INTERVAL_MS + 1
    raw = [
        _make_kline(WINDOW_START_MS, "100.10"),
        _make_kline(WINDOW_START_MS + INTERVAL_MS, "101.10"),
        _make_kline(WINDOW_START_MS + 2 * INTERVAL_MS, "102.10"),
    ]
    processed = process("BTCUSDT", raw, now_ms, endpoint="https://api.binance.com", strict_final=False)

    metrics = processed.metrics
    assert metrics.observed_count == 3
    assert metrics.expected_count_for_now == 3
    assert metrics.contiguous is True
    assert metrics.complete is False
    assert metrics.result_integer_times_100 == 10110
    assert metrics.notes == "temporary"


def test_process_final_contiguous() -> None:
    now_ms = WINDOW_END_OPEN_MS + INTERVAL_MS
    raw = [
        _make_kline(WINDOW_START_MS + i * INTERVAL_MS, str(Decimal("1.0") + Decimal(i)))
        for i in range(EXPECTED_FINAL_COUNT)
    ]

    processed = process("ETHUSDT", raw, now_ms, endpoint="https://api.binance.com", strict_final=False)
    metrics = processed.metrics

    assert metrics.complete is True
    assert metrics.contiguous is True
    assert metrics.notes == "final"
    # Average of arithmetic sequence: first=1, last=720 -> mean 360.5 -> *100 => 36050
    assert metrics.result_integer_times_100 == 36050
    assert processed.exit_code == 0


def test_process_strict_final_failure() -> None:
    now_ms = WINDOW_END_OPEN_MS + INTERVAL_MS
    raw = [
        _make_kline(WINDOW_START_MS + i * INTERVAL_MS, "200.00")
        for i in range(EXPECTED_FINAL_COUNT)
        if i != 100
    ]
    processed = process("BTCUSDT", raw, now_ms, endpoint="https://api.binance.com", strict_final=True)
    metrics = processed.metrics

    assert metrics.complete is False or metrics.contiguous is False
    assert metrics.notes == "error"
    assert processed.exit_code == 2


class _FakeClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses
        self.calls: int = 0

    def get(self, url: str, *, params: dict[str, object], timeout: float) -> httpx.Response:
        if self.calls >= len(self._responses):
            raise httpx.ConnectError("connection issue", request=httpx.Request("GET", url))
        response = self._responses[self.calls]
        self.calls += 1
        return response


def test_fetch_klines_uses_fallback() -> None:
    base_urls = ["https://primary.example", "https://secondary.example"]
    failure_response = httpx.Response(
        503,
        request=httpx.Request("GET", "https://primary.example/api/v3/klines"),
    )
    success_payload = [_make_kline(WINDOW_START_MS, "1.0")]
    success_response = httpx.Response(
        200,
        json=success_payload,
        request=httpx.Request("GET", "https://secondary.example/api/v3/klines"),
    )
    client = _FakeClient([failure_response, success_response])

    outcome = fetch_klines(
        "BTCUSDT",
        client=client,
        base_urls=base_urls,
        start_time_ms=WINDOW_START_MS,
        limit=EXPECTED_FINAL_COUNT,
        sleeper=lambda _: None,
        backoff_seconds=0.0,
    )

    assert outcome.endpoint == "https://secondary.example"
    assert outcome.klines == success_payload


def test_fetch_klines_raises_after_retries() -> None:
    base = "https://primary.example"
    failure_response = httpx.Response(
        500,
        request=httpx.Request("GET", f"{base}/api/v3/klines"),
    )
    client = _FakeClient([failure_response, failure_response, failure_response])

    with pytest.raises(FetchError):
        fetch_klines(
            "ETHUSDT",
            client=client,
            base_urls=[base],
            start_time_ms=WINDOW_START_MS,
            limit=EXPECTED_FINAL_COUNT,
            sleeper=lambda _: None,
            backoff_seconds=0.0,
        )
