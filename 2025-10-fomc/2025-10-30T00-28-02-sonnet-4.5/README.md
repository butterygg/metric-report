# Binance TWAP Calculator

12-hour Time-Weighted Average Price (TWAP) calculator for Binance spot prices.

## Overview

This tool computes the 12-hour TWAP of Binance BTCUSDT or ETHUSDT spot prices as the simple average of exactly 720 one-minute close prices from Binance 1m klines.

**Target window**: 2025-10-29 18:00:00 UTC through 2025-10-30 05:59:00 UTC (both inclusive)

**Output**: Integer representing the TWAP multiplied by 100 and rounded half-up (preserves two decimal places)

## Installation

This project uses Python 3.11+ with uv for dependency management.

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .
```

## Usage

### Basic usage

```bash
# Calculate TWAP for BTC
binance-twap --symbol BTCUSDT

# Calculate TWAP for ETH
binance-twap --symbol ETHUSDT
```

### Advanced options

```bash
# Custom output paths
binance-twap --symbol BTCUSDT \
  --out-json ./results/btc_result.json \
  --raw-out ./results/btc_raw.json

# Strict mode (exit code 2 if final but not contiguous)
binance-twap --symbol ETHUSDT --strict-final

# Use fallback exchange
binance-twap --symbol BTCUSDT --exchange-base https://api-gcp.binance.com
```

### Help

```bash
binance-twap --help
```

## Output

### stdout

**When window is complete and contiguous**:
```
12345678
```
Only the result integer is printed.

**When window is incomplete (temporary TWAP)**:
```
12340000
Temporary TWAP: 350/720 candles (contiguous)
```

**When there are gaps**:
```
12345678
ERROR: Final run but not contiguous (missing 5 candles)
```

### JSON diagnostics

Written to `--out-json` (default: `./twap_result.json`):

```json
{
  "symbol": "BTCUSDT",
  "interval": "1m",
  "window_start_iso": "2025-10-29T18:00:00Z",
  "window_end_open_iso": "2025-10-30T05:59:00Z",
  "now_iso": "2025-10-30T06:30:00.123Z",
  "effective_end_open_iso": "2025-10-30T05:59:00Z",
  "observed_count": 720,
  "expected_count_for_now": 720,
  "complete": true,
  "contiguous": true,
  "missing_open_times_ms": [],
  "twap_mean": "123456.789012345",
  "result_integer_times_100": 12345679,
  "notes": "final",
  "source": {
    "endpoint": "https://api.binance.com",
    "request_params": {
      "symbol": "BTCUSDT",
      "interval": "1m",
      "startTime": 1761760800000,
      "limit": 720
    }
  }
}
```

### Raw klines

Written to `--raw-out` (default: `./klines_raw.json`): Contains the raw Binance API response for auditability.

## Exit codes

- `0`: Success (temporary or final TWAP computed)
- `2`: Final run completed but data is not contiguous (gaps detected)
- `3`: Network failure after all retries and fallback exchanges

## Implementation details

- Uses Python's `Decimal` for precise arithmetic with half-up rounding
- Validates symbol against allowlist (BTCUSDT, ETHUSDT)
- Excludes currently-forming minute candles
- Checks contiguity and ordering of klines
- Retries failed requests up to 3 times per exchange
- Falls back to alternative Binance endpoints on failure
- Handles rate limiting (429) and server errors (5xx)

## Specification

Full specification: [_spec/01-binance-twap.md](../_spec/01-binance-twap.md)

## Examples

### During the window (temporary TWAP)

```bash
$ binance-twap --symbol BTCUSDT
12340000
Temporary TWAP: 350/720 candles (contiguous)
```

### After the window completes

```bash
$ binance-twap --symbol BTCUSDT
12345679
```

### Both symbols

```bash
$ binance-twap --symbol BTCUSDT --out-json btc.json
12345679

$ binance-twap --symbol ETHUSDT --out-json eth.json
567890
```
