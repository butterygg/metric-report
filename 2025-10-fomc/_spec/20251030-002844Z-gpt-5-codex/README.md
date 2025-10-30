# Binance 12-hour TWAP

Executable package for computing the 12-hour TWAP of Binance spot symbols `BTCUSDT`
and `ETHUSDT` over the fixed `2025-10-29T18:00:00Z` → `2025-10-30T05:59:00Z` window.

## Usage

```bash
uv run binance-twap --symbol BTCUSDT
```

Available flags:

- `--symbol {BTCUSDT,ETHUSDT}` (required)
- `--exchange-base URL` — may be provided multiple times to define fallback hosts
- `--out-json PATH` — diagnostics output (default `./twap_result.json`)
- `--raw-out PATH` — raw klines dump (default `./klines_raw.json`)
- `--strict-final` — exit with code `2` unless 720 contiguous minutes are present

`--start` and `--end-open` default to the canonical window; overriding them is rejected.

## Behaviour

- Final contiguous run prints only the resulting integer to stdout.
- Temporary or error runs print the integer (or `null`) followed by a status line.
- Diagnostics JSON records observed counts, contiguity gaps, and metadata needed for audit.
- Raw klines are written verbatim for reproducibility.

⚠️ Binance public REST access is required; the CLI automatically retries across well-known
Binance API hosts on 429/5xx responses.

Exit codes:

- `0` — successful run (final or temporary)
- `2` — strict-final violation or final window gaps
- `3` — network failure after retries

## Development

```bash
uv sync
uv run pytest
uv run ruff check
uv run mypy
```
