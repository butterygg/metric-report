# Spec: BTC/USD TWAP after the U.S. shutdown ends (CoinMarketCap detail chart)

## 1. Objective
Compute the Resolution metric for the **btc-us-shutdown-ends** question by taking a 12-hour TWAP-style snapshot of BTC/USD prices from the CoinMarketCap detail/chart API. The market already resolved (funding lapse ended and agencies reopened) **before** the decision window closed, so this spec always anchors the pricing window to the **actual decision timestamp supplied by the operator**. The result is an **unsigned integer** equal to `ceil(median_price * 100)` for that window.

## 2. Required operator input
- `--decision-time "<ISO8601>"` (preferred) or `--decision-time-epoch <seconds>`: UTC timestamp when funding was restored and OPM status switched back to "Open" (e.g., enactment of the relevant continuing resolution).
  - Must be sourced from the same evidence set used to answer Reality.eth (OPM alert + enrolled CR/appropriations law).
  - Validate it lies within the event window (`2025-11-07T00:00:00Z ≤ decision_time ≤ 2025-11-14T00:00:00Z`).
- Optional switches (diagnostics): `--artifacts <dir>` for JSON dumps, `--raw-points <path>` to store the API payload, `--stdout-json` for machine-readable summary.

Because the decision occurred before the market closed, **do not** substitute the market end timestamp; the CLI must fail if the operator does not provide a decision time.

## 3. Derived window and constants
- `MARKET_END_ISO = 2025-11-14T00:00:00Z` (epoch `1763078400`). Only used for validation / capping.
- `decision_time_epoch = min(operator_supplied, MARKET_END_EPOCH)` (guard against bad inputs, though a valid run should always be `< MARKET_END`).
- `WINDOW_START = decision_time_epoch + 43_200` (12 hours after the decision).
- `WINDOW_END = WINDOW_START + 43_200` (half-open interval; `WINDOW_START ≤ t < WINDOW_END`).
- Expected ISO helpers for logs: `window_start_iso`, `window_end_iso`.
- Instrument constants: `CMC_ASSET_ID = 1` (BTC), `CMC_CONVERT_ID = 2781` (USD).

## 4. Data source and fetch plan
Use CoinMarketCap's detail/chart endpoint:
```
GET https://api.coinmarketcap.com/data-api/v3/cryptocurrency/detail/chart
    ?id=1
    &convertId=2781
    &range=<WINDOW_START>~<WINDOW_END>
```
- `<WINDOW_START>`/`<WINDOW_END>` are the Unix seconds derived above.
- Retry on 5xx/timeout up to 3x with exponential backoff. If all retries fail, exit with a non-zero status and persist diagnostics.
- Store the raw JSON under `--raw-points` for auditability.

## 5. Normalizing samples (`data.points`)
The response encodes a dictionary `data.points` keyed by timestamps. For each `(ts, point)`:
1. If `ts > 10_000_000_000`, treat it as milliseconds; divide by 1000 to convert to seconds (integer floor).
2. Extract the USD price:
   - Prefer `point.v[0]` if the vector exists.
   - Otherwise fall back to `point.c`.
3. Reject the sample if the extracted price is `null`, `NaN`, or `≤ 0`.
4. Keep only the samples whose timestamps satisfy `WINDOW_START ≤ ts < WINDOW_END`.
5. Collect `(ts, price_decimal)` pairs sorted by timestamp asc.

Log `observed_count` and the earliest/latest timestamps. If the API returns zero valid points, exit with a non-zero code and mark the run as inconclusive (we cannot compute the TWAP).

## 6. TWAP proxy calculation (median of valid points)
- Treat the surviving price list as equally-weighted samples over the 12-hour window.
- Compute the **median** (50th percentile) using decimal arithmetic:
  - Odd count `n`: median is element `sorted_prices[(n-1)/2]`.
  - Even count `n`: median is the average of the middle two prices, still using exact decimal math.
- Multiply the median by 100 and apply `ceil` (round toward `+∞`) to obtain the final unsigned integer reported to Reality.eth.

Alongside the integer, capture diagnostics:
```json
{
  "question": "btc-us-shutdown-ends",
  "decision_time_iso": "...",
  "window_start": {
    "iso": "...",
    "epoch": WINDOW_START
  },
  "window_end": {
    "iso": "...",
    "epoch": WINDOW_END
  },
  "observed_count": <n>,
  "median_price": "<decimal string>",
  "result_integer_times_100": <unsigned int>
}
```

## 7. Output contract
- **Stdout** (final run): write only the integer result.
- **Stdout** (error/incomplete): print `null` plus a short explanation on stderr.
- **Artifacts**: store raw payload + derived stats under the operator-provided directory.

## 8. Edge cases & validation
- Reject runs where `decision_time_epoch` is missing, is ≥ `MARKET_END_EPOCH`, or lies outside the allowed event window.
- If the API returns timestamps outside the requested range, keep filtering locally; no assumption about cadence or count is required.
- Make sure the interval is treated as half-open to avoid double-counting `WINDOW_END`.
- Guard against duplicate timestamps by de-duplicating (keep the last sample for a given `ts`).
- Surface the ISO8601 `decision_time` in every log so auditors can trace when the TWAP clock began.
