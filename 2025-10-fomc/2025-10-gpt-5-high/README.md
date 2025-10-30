# 2025-10 FOMC — Binance TWAP CLI

This folder contains a small Python CLI that computes the 12-hour TWAP for Binance spot `BTCUSDT` or `ETHUSDT` using 1m klines, per the spec in `../_spec/01-binance-twap.md`.

- Window: 2025-10-29 18:00:00 UTC → 2025-10-30 05:59:00 UTC (inclusive)
- Output: unsigned integer = ROUND_HALF_UP(mean * 100)
- Writes diagnostics JSON and raw klines JSON; prints primary result to stdout.

## Usage

- Show help: `python3 script/twap.py -h`
- BTC: `python3 script/twap.py --symbol BTCUSDT`
- ETH: `python3 script/twap.py --symbol ETHUSDT`
- Strict final (fail if final window is non-contiguous): `python3 script/twap.py --symbol BTCUSDT --strict-final`

Each run creates a folder inside this package directory named `<ISO8601-UTC-timestamp>-<model_name>` where outputs are saved by default (unless `--no-run-dir` is used).
