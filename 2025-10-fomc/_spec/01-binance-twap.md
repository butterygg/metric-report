# Spec: 12-hour TWAP (Binance spot, 1m klines) — **parameterized symbol**

## 1) Objective

Compute an **unsigned integer** equal to the **12-hour TWAP** of a **Binance spot** symbol (default: `BTCUSDT`, also required for your second question: `ETHUSDT`), defined as the **simple average of exactly 720 one-minute close prices** from Binance **1m** klines, over the UTC window:

* **Start (inclusive):** `2025-10-29 18:00:00 UTC`
* **End (inclusive):** `2025-10-30 05:59:00 UTC`

Then **multiply by 100** and **round half-up** to the nearest integer (two decimals → integer).

Additionally, if the 12-hour window hasn’t finished yet, output a **temporary TWAP** from **start** through **min(now, end)** using only **fully closed** 1-minute candles.

## 2) Inputs (CLI / config)

* `--symbol` (string, **required**): **`BTCUSDT`** or **`ETHUSDT`**.

  * Validate against an allow-list: `{"BTCUSDT","ETHUSDT"}` (fail fast if outside).
* `--start "2025-10-29T18:00:00Z"` (default fixed)
* `--end-open "2025-10-30T05:59:00Z"` (default fixed)
* `--exchange-base` (default `https://api.binance.com`) with optional fallback list.
* `--out-json` (JSON diagnostics path; default `./twap_result.json`)
* `--raw-out` (raw klines path; default `./klines_raw.json`)
* `--strict-final` (if set, final run **must** have exactly 720 contiguous minutes, else error code)

## 3) Canonical window & epochs (constants)

* `window_start_iso = "2025-10-29T18:00:00Z"`
* `window_end_open_iso = "2025-10-30T05:59:00Z"`  (this is the **open time** of the **last included** 1-minute candle)
* Epochs (ms, UTC):

  * `window_start_ms = 1761760800000`
  * `window_end_open_ms = 1761803940000`
* `expected_final_count = 720`

## 4) Data source

**Binance Spot REST API** `GET /api/v3/klines`
Params: `symbol`, `interval=1m`, `startTime`, `limit` (≤1000).
We will **post-filter** locally to enforce the dynamic end boundary (see §6).

## 5) Temporary TWAP (before the window ends)

At runtime `now_utc_ms`:

```
last_closed_minute_open_ms = floor(now_utc_ms to minute) - 60_000
effective_end_open_ms = min(window_end_open_ms, last_closed_minute_open_ms)
```

* If `effective_end_open_ms < window_start_ms`: `observed_count = 0` (no data yet).
* Else: expected partial count
  `expected_partial_count = ((effective_end_open_ms - window_start_ms)/60000) + 1`

**Always exclude** the still-forming current minute.

## 6) Fetch plan

One request suffices (720 ≤ 1000):

```
GET /api/v3/klines
  ?symbol=<SYMBOL>
  &interval=1m
  &startTime=1761760800000
  &limit=720
```

* **Do not** pass `endTime`; **post-filter** by `openTime <= effective_end_open_ms`.
* If short vs `expected_partial_count`, retry up to 3x with small backoff.
* If host is 429/5xx/timeouts, rotate to alternates (e.g., `api-gcp.binance.com`, `api1.binance.com`…).

## 7) Validation

On the post-filtered array:

1. **Ordering & contiguity**: `openTime` must equal `window_start_ms + i*60_000`.

   * Temporary run: if gaps, set `contiguous=false`, list missing minutes, but still compute TWAP over observed candles.
   * Final run (720 candles): if any gap → fail (strict: **exactly** 720 consecutive minutes required).
2. **Interval/symbol check**: assert `interval == "1m"`, `symbol` equals input.
3. **Field parsing**: parse `close` (index 4) as **decimal** (not binary float).

## 8) TWAP math (decimal + half-up)

* `mean = (Σ Decimal(close_i)) / N`
* `result_integer_times_100 = ROUND_HALF_UP(mean * 100)` → cast to unsigned integer.
* Use true **half-up** rounding (not bankers rounding).

## 9) Outputs

**Human stdout:**

* **Final (complete & contiguous):** print **only** `result_integer_times_100` on the first line.
* **Temporary / error:** print the integer or `null`, then a short status line.

**JSON diagnostics (`--out-json`):**

```json
{
  "symbol": "<BTCUSDT|ETHUSDT>",
  "interval": "1m",
  "window_start_iso": "2025-10-29T18:00:00Z",
  "window_end_open_iso": "2025-10-30T05:59:00Z",
  "now_iso": "<runtime>",
  "effective_end_open_iso": "<derived>",
  "observed_count": <N>,
  "expected_count_for_now": <expected_partial_count>,
  "complete": <true|false>,
  "contiguous": <true|false>,
  "missing_open_times_ms": [ ... ],
  "twap_mean": "<decimal string>",
  "result_integer_times_100": <unsigned int or null>,
  "notes": "temporary|final|error",
  "source": {
    "endpoint": "<base-url-used>",
    "request_params": {
      "symbol": "<...>",
      "interval": "1m",
      "startTime": 1761760800000,
      "limit": 720
    }
  }
}
```

Also write raw klines to `--raw-out` for auditability.

## 10) Exit codes

* `0` = success (temporary or final, see JSON flags)
* `2` = **final** run but not exactly 720 contiguous minutes
* `3` = network failure after retries

## 11) Pseudocode

```pseudo
INPUT SYMBOL in {"BTCUSDT","ETHUSDT"}

CONST START_MS = 1761760800000
CONST END_OPEN_MS = 1761803940000
CONST INTERVAL_MS = 60000
CONST LIMIT = 720

now_ms = utc_now_ms()
last_closed_open_ms = floor_to_minute(now_ms) - INTERVAL_MS
effective_end_open_ms = min(END_OPEN_MS, last_closed_open_ms)

if effective_end_open_ms < START_MS:
    observed = []
else:
    klines = http_get_klines(symbol=SYMBOL, interval="1m",
                             startTime=START_MS, limit=LIMIT)  // with retries/fallbacks
    observed = [k for k in klines if k.openTime <= effective_end_open_ms]
    observed = sort_by_openTime(observed)

expected_partial_count = (effective_end_open_ms >= START_MS)
  ? ((effective_end_open_ms - START_MS)/INTERVAL_MS) + 1
  : 0

// contiguity
contiguous = true
missing = []
for i in 0..len(observed)-1:
    expect = START_MS + i*INTERVAL_MS
    if observed[i].openTime != expect:
        contiguous = false
        // build full missing list by diffing expected sequence vs actual opens

N = len(observed)
if N == 0:
    mean = null
    result = null
else:
    closes = [Decimal(k.close) for k in observed]
    mean = sum(closes)/Decimal(N)
    result = ROUND_HALF_UP(mean * 100)  // unsigned int

complete = (N == 720) && (effective_end_open_ms == END_OPEN_MS)

if complete && !contiguous:
    exit 2
else:
    emit_stdout_and_json(result, diagnostics)
    exit 0
```

## 12) Acceptance tests

1. **Symbol switching**

   * Run with `--symbol BTCUSDT` and `--symbol ETHUSDT`; both produce well-formed outputs.
2. **Early run** (before 18:00Z): `observed_count=0`, `result=null`, `complete=false`.
3. **Mid-window**: counts match elapsed minutes; `contiguous=true`; integer present.
4. **Final window**: `observed_count=720`, `contiguous=true`, prints only the integer on line 1.
5. **Injected gap** at final: exit `2`, `contiguous=false`, missing minutes listed.

## 13) Implementation notes

* Use **decimal/bignum** arithmetic with **half-up** rounding.
* Always exclude the currently forming minute.
* Keep allow-list for symbols to avoid accidentally hitting the wrong market.
* Persist artifacts (raw and computed) for reproducibility; same inputs → same integer.

---

If you want, I can now generate a compact **Python** or **Node** reference implementation that follows this spec and lets you switch `--symbol BTCUSDT|ETHUSDT` on the CLI.
