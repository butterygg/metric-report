# CFM metrics

This repository contains scripts to compute metrics used to resolve CFM
conditional markets.

These scripts are also used to track candidate projects' progress along the way.

## HYPE/USDC 12h TWAP CLI

A spec-compliant CLI is available to compute the Reality.eth metric defined in `spec.md`.

Usage examples:

- `uv run hype-twap --decision-time "2025-09-18T17:03:00Z"`
- `uv run hype-twap --decision-time-ms 1758205380000`

Flags:

- `--artifacts <dir>`: directory to write artifacts (default: `artifacts`)
- `--allow-early`: allow computing before `T_e + 5m` (non-zero exit otherwise)
- `--verbose`: extra logs to stderr

Output:

- Prints only the final integer (cents) to stdout.
- Writes `artifacts/spotMeta.json`, `artifacts/candles.json`, `artifacts/closes.csv`, `artifacts/result.json`.

Note: The CLI uses the Hyperliquid Info API over HTTPS; ensure network access is available when running.
