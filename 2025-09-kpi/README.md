USDC Aave V3 Ethereum — 30-day Base APY (Trailing to 2025-09-25)

- Source: `https://yields.llama.fi/chart/aa70268e-4b52-42bf-a116-608b370f9501`
- Metric: Supply APY excluding rewards (`apyBase`)
- Window: 30 calendar days, UTC, from 2025-08-27 through 2025-09-25 inclusive

Result

- 30-day trailing average (base APY): 451 bps

Artifacts

- Raw payload: `@2025-09-26-kpi/defillama_yields_usdc_aavev3_eth_raw.json`
- Script: `@2025-09-26-kpi/compute_usdc_aavev3_eth_30d_avg.py`

Usage

- Run: `python3 @2025-09-26-kpi/compute_usdc_aavev3_eth_30d_avg.py`
- The script fetches the latest data, persists the raw JSON, prints each daily base APY used, and outputs the 30-day average in basis points.

Notes

- Each day is treated by its UTC calendar date. If multiple intra-day points exist, the script computes the daily mean of `apyBase` for that date, then averages those 30 daily values equally.

USDT Aave V3 Ethereum — 30-day Base APY (Trailing to 2025-09-25)

- Source: `https://yields.llama.fi/chart/f981a304-bb6c-45b8-b0c5-fd2f515ad23a`
- Metric: Supply APY excluding rewards (`apyBase`)
- Window: 30 calendar days, UTC, from 2025-08-27 through 2025-09-25 inclusive

Result

- 30-day trailing average (base APY): 469 bps

Artifacts

- Raw payload: `@2025-09-26-kpi/defillama_yields_usdt_aavev3_eth_raw.json`
- Script: `@2025-09-26-kpi/compute_usdt_aavev3_eth_30d_avg.py`

Usage

- Run: `python3 @2025-09-26-kpi/compute_usdt_aavev3_eth_30d_avg.py`
- The script fetches the latest data, persists the raw JSON, prints each daily base APY used, and outputs the 30-day average in basis points.

Base Chain — 30-day Daily Revenue (Trailing to 2025-09-26)

- Source: `https://api.llama.fi/summary/fees/base?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true&dataType=dailyRevenue`
- Metric: Daily revenue in USD
- Window: 30 calendar days, UTC, from 2025-08-28 through 2025-09-26 inclusive

Result

- 30-day trailing average (daily revenue): $155,761

Artifacts

- Raw payload: `@2025-09-26-kpi/defillama_fees_base_daily_revenue_raw.json`
- Script: `@2025-09-26-kpi/compute_base_daily_revenue_30d_avg.py`

Usage

- Run: `python3 @2025-09-26-kpi/compute_base_daily_revenue_30d_avg.py`
- The script fetches the latest fees data, persists the raw JSON, prints each daily revenue used, and outputs the 30-day average rounded to integer USD.

Notes

- Each day is treated by its UTC calendar date. If the series has multiple entries for a date, the script averages them for that day, then averages the 30 daily values equally. Missing days are reported and excluded from the averaging.

Base Chain — TVL at 2025-09-26 00:00 UTC

- Source: `https://api.llama.fi/v2/historicalChainTvl/Base`
- Metric: Total TVL (USD) at exact timestamp 2025-09-26 00:00:00 UTC

Result

- TVL: $4,751,981,453

Artifacts

- Raw payload: `@2025-09-26-kpi/defillama_chain_base_tvl_raw.json`
- Script: `@2025-09-26-kpi/compute_base_tvl_2025_09_26_utc00.py`

Usage

- Run: `python3 @2025-09-26-kpi/compute_base_tvl_2025_09_26_utc00.py`
- The script fetches the daily TVL series, prints the matched data point at 2025-09-26 00:00 UTC, and outputs the integer USD value.

Generic TVL Script at 2025-09-26 00:00 UTC

- Script: `@2025-09-26-kpi/compute_chain_tvl_at_2025_09_26_utc00.py`
- Usage: `python3 @2025-09-26-kpi/compute_chain_tvl_at_2025_09_26_utc00.py Base Solana "Hyperliquid L1"`
- Results:
  - Base: $4,751,981,453
  - Solana: $10,763,911,176
  - Hyperliquid L1: $2,020,317,157

ETH.STORE — 30-day APR (Trailing to 2025-09-25)

- Source: `https://beaconcha.in/api/v1/ethstore/{day}` where `{day}` is a day identifier. The script tries common formats and supports an optional API key.
- Metric: ETH.STORE daily APR (`apr`), using the UTC calendar date of the `day_end` field per observation.
- Window: 30 calendar days, UTC, from 2025-08-27 through 2025-09-25 inclusive

Result

- 30-day trailing average (APR): 287 bps

Script

- `@2025-09-26-kpi/compute_ethstore_apr_30d_avg.py`
- Behavior:
  - Fetches each day’s ETH.STORE entry across the 30-day window.
  - Prints every daily APR used (percent and bps) keyed by `day_end` UTC date.
  - Computes the 30-day average in integer basis points.
- API key: If available, set `BEACONCHAIN_API_KEY` in your environment. The script will send it via `X-API-KEY` header and `apikey` query parameter for compatibility.

Usage

- Run: `python3 @2025-09-26-kpi/compute_ethstore_apr_30d_avg.py`
- Output: per-day APR values followed by the 30-day average in bps. The script discovers the correct numeric `day` IDs (e.g., 1729..1758) by parsing `day_end` and only uses daily observations (no rolling averages).
