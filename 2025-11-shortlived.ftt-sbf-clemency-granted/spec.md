# Spec: FTT/USD TWAP for the SBF clemency cutoff (CoinMarketCap detail chart)

## 1. Objective
Produce the metric for **ftt-sbf-clemency-granted** by sampling FTT/USD prices 12–24 hours after the market's end (`2025-11-14T00:00:00Z`). Reality resolved "No clemency" before that cutoff, so the pricing window is fixed relative to the cutoff rather than a specific decision event. The output is the unsigned integer `ceil(median_price * 100)` derived from CoinMarketCap's detail/chart API.

## 2. Time anchors (fixed)
- `MARKET_END_ISO = 2025-11-14T00:00:00Z` (epoch `1763078400`).
- `DECISION_TIME = MARKET_END_ISO` (no White House clemency posting before the window closed).
- `WINDOW_START = 2025-11-14T12:00:00Z` (epoch `1763121600`).
- `WINDOW_END = 2025-11-15T00:00:00Z` (epoch `1763164800`, exclusive).

Document in the run logs that the TWAP window is anchored to the cutoff because no qualifying decision happened.

## 3. API request
```
GET https://api.coinmarketcap.com/data-api/v3/cryptocurrency/detail/chart
    ?id=4195
    &convertId=2781
    &range=1763121600~1763164800
```
- `id=4195` corresponds to FTT.
- `convertId=2781` requests USD quotes.
- Use the same retry/backoff policy as the BTC specs and persist the raw JSON payload.

## 4. Sample normalization & filtering
Follow the identical steps:
1. Iterate `data.points` → `(timestamp, sample)` pairs.
2. Convert millisecond timestamps to seconds when `ts > 10_000_000_000`.
3. Extract USD price via `point.v[0]` or `point.c`.
4. Drop any sample whose price is missing/NaN/≤ 0.
5. Keep only timestamps `t` where `WINDOW_START ≤ t < WINDOW_END`.
6. Sort the survivors by timestamp.

If no valid samples remain, exit with an error (cannot compute the metric) and log the empty-set condition.

## 5. Median/TWAP math and rounding
- Compute the median (odd/even cases) in decimal precision.
- Multiply by 100.
- Apply `ceil` to obtain the unsigned integer reported to Reality.eth.

Diagnostics example:
```json
{
  "question": "ftt-sbf-clemency-granted",
  "decision_time_iso": "2025-11-14T00:00:00Z",
  "window_start_iso": "2025-11-14T12:00:00Z",
  "window_end_iso": "2025-11-15T00:00:00Z",
  "observed_count": <n>,
  "median_price": "<decimal>",
  "result_integer_times_100": <unsigned int>
}
```

## 6. Output & validation
- Stdout: final integer on success, nothing else.
- Stderr / JSON diagnostics warn if the run is temporary or missing data.
- The CLI should mention (in notes/metadata) that the TWAP is the post-cutoff window because no clemency grant occurred before the end of the question.
