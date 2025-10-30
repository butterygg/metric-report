# Goal

Build two scripts able to produce the data expected by the following questions:

## BTC

Return an unsigned integer equal to the 12-hour TWAP of the Binance BTCUSDT spot price, computed as the simple average of exactly 720 one-minute close prices from Binance 1m klines for symbol BTCUSDT, covering 2025-10-29 18:00:00 UTC through 2025-10-30 05:59:00 UTC (both endpoints included). Multiply by 100 and round half-up to the nearest integer (two decimals).

## ETH

Return an unsigned integer equal to the 12-hour TWAP of the Binance ETHUSDT spot price, computed as the simple average of exactly 720 one-minute close prices from Binance 1m klines for symbol ETHUSDT, covering 2025-10-29 18:00:00 UTC through 2025-10-30 05:59:00 UTC (both endpoints included). Multiply by 100 and round half-up to the nearest integer (two decimals).


# Spec

Build an executable package that can be called against BTCUSDT or ETHUSDT (for
example, based on a parameter passed as CLI argument).

Follow the precise spec in [01](./01-binance-twap.md).

Produce a folder which name contains the exact timestamp (readable human format)
and the name of your model (e.g. gpt-5 or gpt-5-codex or sonnet-4.5) in the
following format: `$timestamp-$model_name`. This folder should be created in the
folder parent to this current file.

The executable should be callable from a shell and have a `-h` or `--help` flag
that prints out a detailed explanation of how to launch it and what results to
expect.

The output should be produced on stdout.
