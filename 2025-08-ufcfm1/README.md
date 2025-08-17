# Unichain TVL Analysis

Calculate 30-day trailing average of Total Value Locked (TVL) + Borrowed TVL for any protocol on Unichain using DeFiLlama API.

## Script

### `calculate_unichain_tvl.py`
Calculates the 30-day trailing average for a given protocol on Unichain by:
- Fetching protocol data from DeFiLlama API
- Extracting both `Unichain` TVL data and `Unichain-borrowed` data
- Processing daily data points for the 30-day period ending on August 10, 2025
- Summing TVL + Borrowed TVL for each day
- Computing the average and rounding DOWN to the nearest integer (for Reality.eth)

## Requirements

- Python 3.x
- `requests` library

## Usage

```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install requests

# Run calculation for any protocol
python calculate_unichain_tvl.py <protocol-slug>

# Example for Venus Core Pool
python calculate_unichain_tvl.py venus-core-pool
```

## API

The script queries DeFiLlama API at:
- Base URL: `https://api.llama.fi/protocol/{protocol-slug}`
- Protocol slugs can be found at: `https://api.llama.fi/protocols`

## Example Result

Venus 30-day trailing average (July 12 - August 10, 2025): **$14,850,025** (rounded down)