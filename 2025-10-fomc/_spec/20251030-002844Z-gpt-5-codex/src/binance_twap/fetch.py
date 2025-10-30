from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

import httpx

DEFAULT_BASE_URLS: tuple[str, ...] = (
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api-gcp.binance.com",
)


class SupportsGet(Protocol):
    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> httpx.Response:
        ...


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchOutcome:
    endpoint: str
    klines: list[list[Any]]


def fetch_klines(
    symbol: str,
    *,
    client: SupportsGet,
    base_urls: Sequence[str] | None,
    start_time_ms: int,
    limit: int,
    interval: str = "1m",
    retries: int = 3,
    timeout: float = 10.0,
    backoff_seconds: float = 0.5,
    sleeper: Callable[[float], None] = time.sleep,
) -> FetchOutcome:
    urls = tuple(base_urls) if base_urls else DEFAULT_BASE_URLS
    if not urls:
        raise ValueError("At least one base URL must be provided.")

    errors: list[Exception] = []
    for attempt in range(retries):
        base_url = urls[attempt % len(urls)]
        try:
            response = client.get(
                f"{base_url}/api/v3/klines",
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": start_time_ms,
                    "limit": limit,
                },
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            errors.append(exc)
            _maybe_sleep(backoff_seconds, attempt, sleeper)
            continue

        if response.status_code in {429, 500, 502, 503, 504}:
            errors.append(
                FetchError(
                    f"Transient HTTP status {response.status_code} from {base_url}",
                )
            )
            _maybe_sleep(backoff_seconds, attempt, sleeper)
            continue

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            errors.append(exc)
            _maybe_sleep(backoff_seconds, attempt, sleeper)
            continue

        try:
            payload = response.json()
        except ValueError as exc:
            errors.append(exc)
            _maybe_sleep(backoff_seconds, attempt, sleeper)
            continue

        if not isinstance(payload, list):
            errors.append(FetchError("Unexpected response payload (expected list)."))
            _maybe_sleep(backoff_seconds, attempt, sleeper)
            continue

        return FetchOutcome(endpoint=base_url, klines=payload)

    if errors:
        raise FetchError("Unable to fetch klines after retries.") from errors[-1]
    raise FetchError("Unable to fetch klines after retries.")


def _maybe_sleep(backoff_seconds: float, attempt: int, sleeper: Callable[[float], None]) -> None:
    delay = max(backoff_seconds * (attempt + 1), 0.0)
    if delay > 0:
        sleeper(delay)
