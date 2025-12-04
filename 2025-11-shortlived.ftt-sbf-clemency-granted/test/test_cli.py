from __future__ import annotations

from types import SimpleNamespace
from decimal import Decimal

import pytest

from metric_report.cli import (
    CONFIG,
    MetricError,
    ceil_cents,
    collect_window_prices,
    compute_window,
    median_price,
    resolve_decision_epoch,
)


def make_args(**kwargs):
    defaults = {
        "decision_time": None,
        "decision_time_epoch": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_resolve_decision_epoch_defaults_to_cutoff() -> None:
    epoch = resolve_decision_epoch(make_args(), CONFIG)
    assert epoch == CONFIG.market_end_epoch


def test_resolve_decision_epoch_accepts_iso() -> None:
    args = make_args(decision_time="2025-11-10T05:00:00Z")
    epoch = resolve_decision_epoch(args, CONFIG)
    assert epoch == 1762750800


def test_compute_window_offsets_correctly() -> None:
    start, end = compute_window(100)
    assert start == 100 + 43_200
    assert end == start + 43_200


def test_collect_window_prices_filters_invalid_points() -> None:
    payload = {
        "data": {
            "points": {
                "10": {"v": ["1.0", 2]},  # valid
                "11": {"c": "0"},  # zero price -> drop
                "12": {"v": []},  # missing data -> drop
                "13000": {"v": ["3.0"]},  # outside window
                "13000000000": {"v": ["2.0"]},  # ms timestamp -> 13000000
                "bad": {"v": ["4.0"]},  # cannot parse ts
            }
        }
    }
    prices, range_info = collect_window_prices(payload, start=10, end=20)
    # Expect timestamps at 10 and (13000000000 // 1000 == 13000000) filtered out, so only ts 10
    assert prices == [Decimal("1.0")]
    assert range_info["earliest_epoch"] == 10


def test_median_and_ceil_cents() -> None:
    prices = [Decimal("2"), Decimal("4"), Decimal("6"), Decimal("8")]
    med = median_price(prices)
    assert med == Decimal("5")
    assert ceil_cents(Decimal("1.234")) == 124


def test_collect_window_prices_returns_empty_for_missing_data() -> None:
    payload = {"data": {"points": {"1": {"v": ["-1"]}}}}
    prices, range_info = collect_window_prices(payload, start=10, end=20)
    assert prices == []
    assert range_info is None


def test_resolve_decision_epoch_clamps_future_times() -> None:
    args = make_args(decision_time_epoch=CONFIG.market_end_epoch + 1)
    epoch = resolve_decision_epoch(args, CONFIG)
    assert epoch == CONFIG.market_end_epoch
