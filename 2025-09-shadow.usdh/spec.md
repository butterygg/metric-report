# HYPE/USDC 12h TWAP — Coding Agent Spec (Reality.eth Metric)

**Goal:** Build a small CLI tool that computes the metric defined in our Oracle Rules:

> Return an unsigned integer equal to the **12-hour TWAP** of the **HYPE/USDC spot** price on **Hyperliquid**, starting **exactly 120 minutes after** the decision time **T\_d** (UTC). The TWAP is the **simple average** of **1-minute close** prices from Hyperliquid’s **Info API** for the HYPE/USDC **spot** pair, then **×100** and **rounded half-up** to the nearest integer (**cents**).

This spec intentionally avoids code details. It describes the **API**, **inputs/outputs**, **time math**, **edge cases**, and the **artifacts** you must write so we can compare run-by-run outputs with another implementation.

---

## 1) Inputs (from caller)

* **Decision time `T_d` (UTC)** — Provided by the caller, **already determined** per Section A.3 of the Rules (Tier A precedence; fallback if no Tier A). The tool **must not** discover/scrape the decision time; accept it as input.

Accepted forms (support both):

* `--decision-time "<ISO8601>Z"` e.g. `2025-09-18T17:03:00Z`
* `--decision-time-ms <epoch_ms>` e.g. `1758205380000`

Optional:

* `--artifacts <dir>` (where to save files; default you choose)
* `--verbose`
* `--allow-early` (allow computing before earliest-answerable; off by default)

---

## 2) Time anchors (all UTC)

Let:

* **Cooldown:** `120 minutes` after `T_d`.
* **Observation start `T_s` = `T_d` + 120 min.**
  If `T_s` isn’t exactly on a minute boundary (`:ss != 00`), **ceil** to the next full minute to align with 1-minute candles.
* **Window length:** `12 hours` → `720` minutes.
* **Observation end `T_e` = `T_s` + 12 h.**
* **Earliest answerable time:** `T_e + 5 minutes`. If now < this, exit with a clear message (“answered too soon”), unless `--allow-early` is set.

Timestamps passed to the API are **milliseconds since epoch**.

---

## 3) Data source — Hyperliquid Info API (Spot)

Use **REST** `POST https://api.hyperliquid.xyz/info` with JSON bodies.

### 3.1 Resolve the HYPE/USDC **spot** pair (once per run)

* Call `{"type":"spotMeta"}` to fetch **spot metadata** (tokens and spot pairs “universe”). Save the full JSON (see Artifacts). ([hyperliquid.gitbook.io][1])
* Resolve the **pair identifier** by mapping **HYPE** and **USDC** token indices in `tokens` to the entry in `universe` whose `tokens == [HYPE_idx, USDC_idx]`. The **coin identifier** used by Info requests is `@<pairIndex>` (or fall back to the `name` `"HYPE/USDC"` if provided).
  *Why this step?* Symbol/indexing can change; `spotMeta` is the canonical source at execution time. ([hyperliquid.gitbook.io][1])

### 3.2 Retrieve **1-minute** candles over `[T_s, T_e)`

* Call `{"type":"candleSnapshot","req":{"coin":"@<index>","interval":"1m","startTime":<ms>,"endTime":<ms>}}`.
  Response is a list of candles with fields including:
  `t` (candle start ms), `T` (candle end ms), `i` (interval, e.g. `"1m"`), `o/h/l/c/v`. Use **`c` (close)** only. ([hyperliquid.gitbook.io][2])
* **Pagination:** If you don’t receive all items (time-ranged responses are limited), repeat requests advancing `startTime` to the **last returned `T`** (+1 ms) until you cover `[T_s, T_e)`. ([hyperliquid.gitbook.io][2])
* **Rate limits:** Keep requests modest; the documented REST budget is ample for this task. ([hyperliquid.gitbook.io][3])

---

## 4) Minute grid & edge cases

* Build an exact **minute grid**: `[T_s, T_s+1m, ..., T_e-1m]` (length **720**).
* Map returned candles by **`t`** (start ms). For each grid minute:

  * If the minute exists, take its **close**.
  * If **missing**, **carry-forward** the **previous available close**.

    * If the **first** minute is missing, first try to fetch the **preceding minute** `[T_s-1m, T_s)` to seed the carry-forward. If still unavailable, **abort** (not answerable yet).
  * If there are **> 60 consecutive missing minutes**, **abort** (not answerable yet), per our Rules.

Save whether each minute was `actual` or `filled` in the CSV (see Artifacts).

*All times are UTC; all API times are milliseconds since epoch.*

---

## 5) TWAP & rounding

* Let `c_i` be the close for each of the **720** minutes.
  **TWAP (USD)** = simple average = `(1/720) * Σ c_i`.
* **Units**: the API returns price in **USDC per HYPE**; do not rescale decimals.
* **Report** an **unsigned integer** in **cents**:
  `CENTS = round_half_up(TWAP * 100)` with half-up defined as **floor(x + 0.5)** for positive `x`.
  (*Avoid binary float rounding surprises; use decimal/fixed arithmetic.*)

---

## 6) Outputs

* **STDOUT:** print only the final **unsigned integer** `CENTS` (no other text).
* **Exit codes:** non-zero for errors (e.g., “answered too soon”, “not answerable yet due to missing data”, HTTP failures).

---

## 7) Artifacts to write (for reproducibility)

Write the **same files** and structure below so we can compare runs across implementations:

1. `artifacts/spotMeta.json`

   * Entire response of the `spotMeta` call.

2. `artifacts/candles.json`

   * **Concatenated** array of all `candleSnapshot` responses used to cover `[T_s, T_e)` (after pagination). Keep items **as returned**.

3. `artifacts/closes.csv`

   * CSV header: `t_start_ms,t_start_iso,close,source`
   * One row per minute in the 720-minute grid.
   * `source` ∈ `{actual,filled}`.
   * `t_start_iso` format: `YYYY-MM-DDTHH:MM:SSZ`.

4. `artifacts/result.json`

   * Minimal structured summary:

     ```json
     {
       "decision_time_ms": <int>,
       "decision_time_iso": "<str>",
       "observation_start_ms": <int>,
       "observation_start_iso": "<str>",
       "observation_end_ms": <int>,
       "observation_end_iso": "<str>",
       "earliest_answerable_ms": <int>,
       "earliest_answerable_iso": "<str>",
       "n_minutes": 720,
       "twap_usd": "<decimal string>",
       "cents_uint": <int>,
       "coin": "@<pairIndex or name>"
     }
     ```

---

## 8) Acceptance checks

The tool should:

1. **Honor time math** precisely (UTC; minute ceiling at `T_s` if needed; `[T_s, T_e)` exclusivity).
2. **Fail fast** if before `T_e + 5m` (unless `--allow-early`).
3. **Use spotMeta** to resolve HYPE/USDC at runtime (no hard-coding). ([hyperliquid.gitbook.io][1])
4. **Paginate** `candleSnapshot` until the full interval is covered. ([hyperliquid.gitbook.io][2])
5. **Fill gaps** by carry-forward; **abort** on `>60` consecutive missing minutes.
6. **Compute** simple average of closes; **half-up** to cents; **print integer** only.
7. **Write all artifacts** exactly as specified.

---

## 9) Notes & references

* **Info endpoint & pagination behavior** (time-windowed responses, advance using last timestamp). ([hyperliquid.gitbook.io][2])
* **Spot metadata** (`spotMeta`) and spot Info requests. ([hyperliquid.gitbook.io][1])
* **Candle snapshot** request for historical OHLCV windows. ([docs.chainstack.com][4])
* **Supported intervals** include `"1m"` (confirming the 1-minute cadence). ([hyperliquid.gitbook.io][5])
* **Rate limits** (FYI; trivial impact here). ([hyperliquid.gitbook.io][3])

---

## 10) What not to implement

* **Do not** fetch or decide `T_d` from the web. It is **provided** by the caller per our Rules.
* **Do not** use multi-venue data or derivatives; **spot only** on Hyperliquid.
* **Do not** rescale prices beyond the final `×100` to cents; the API already returns USD per HYPE.

---

### Deliverable

A single CLI tool (language of your choice) that follows Sections **1–9**, produces the **four artifacts** verbatim, and prints the **final integer** to stdout.

[1]: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/spot?utm_source=chatgpt.com "Spot - Hyperliquid Docs - GitBook"
[2]: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint?utm_source=chatgpt.com "Info endpoint | Hyperliquid Docs - GitBook"
[3]: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits?utm_source=chatgpt.com "Rate limits and user limits - Hyperliquid Docs - GitBook"
[4]: https://docs.chainstack.com/reference/hyperliquid-info-candle-snapshot?utm_source=chatgpt.com "candleSnapshot | Hyperliquid info"
[5]: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions?utm_source=chatgpt.com "Subscriptions - Hyperliquid Docs - GitBook"
