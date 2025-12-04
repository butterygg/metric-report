# Spec: BTC/USD TWAP for the U.S.–Venezuela engagement cutoff (CoinMarketCap detail chart)

## 1. Objective
Compute the Resolution metric for **btc-us-venezuela-military-engagement** using CoinMarketCap's detail/chart endpoint. Because no qualifying engagement occurred before the market closed, the Decision timestamp defaults to the market's cutoff (`2025-11-14T00:00:00Z`), and we always look **12–24 hours after that cutoff**. The deliverable is `ceil(median_price * 100)` over that window.

## 2. Time anchors (no operator decision input)
- `MARKET_END_ISO = 2025-11-14T00:00:00Z` (epoch `1763078400`). This already reflects the "on or before" clause in the Reality question.
- `DECISION_TIME = MARKET_END_ISO` (hard-coded because Reality resolved "No engagement" during the market window).
- `WINDOW_START = 2025-11-14T12:00:00Z` (epoch `1763121600`).
- `WINDOW_END = 2025-11-15T00:00:00Z` (epoch `1763164800`). Treat as half-open `[start, end)`. These timestamps also match the JSON `openingTimeMetric` values.

If future investigators choose to recompute before final resolution, allow a guard like `--decision-time` that defaults to the cutoff but still caps at `MARKET_END`. For the published replay, it must remain the cutoff.

## 3. Endpoint and parameters
```
GET https://api.coinmarketcap.com/data-api/v3/cryptocurrency/detail/chart
    ?id=1
    &convertId=2781
    &range=1763121600~1763164800
```
- `id=1` → BTC
- `convertId=2781` → USD
- `range` uses the epoch seconds above.
- Retries/backoff per the shutdown spec (§4) and store the raw payload.

## 4. Sample normalization
Identical handling as the shutdown metric:
1. Iterate over `data.points`.
2. Normalize timestamps to seconds (divide ms values by 1000).
3. Extract USD price via `point.v[0]` or `point.c`.
4. Drop invalid or non-positive prices.
5. Keep samples with timestamps in `[WINDOW_START, WINDOW_END)`.
6. Sort asc and log `observed_count`, earliest, and latest timestamps.

## 5. Median/TWAP computation
- Compute the median of the surviving decimal prices.
- Multiply by 100 and `ceil` to produce the unsigned integer answer.
- Capture diagnostics mirroring the structure from the shutdown spec but with the hard-coded window metadata.

Example diagnostics:
```json
{
  "question": "btc-us-venezuela-military-engagement",
  "decision_time_iso": "2025-11-14T00:00:00Z",
  "window_start_iso": "2025-11-14T12:00:00Z",
  "window_end_iso": "2025-11-15T00:00:00Z",
  "observed_count": <n>,
  "median_price": "<decimal>",
  "result_integer_times_100": <unsigned int>
}
```

## 6. Output handling and validation
- Stdout → integer or `null` like before.
- Error if the API yields zero valid points.
- If any sample lies outside the window, filter locally but do not fail.
- Record in the log that the TWAP was anchored to the cutoff (no decision time available) so reviewers understand why the window begins 12 hours after 00:00Z on 14 Nov.
