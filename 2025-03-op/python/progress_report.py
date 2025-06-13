import csv
import sys
from datetime import datetime, timezone

import requests

# Global configuration variables
METRIC_START_DATE = "2025-03-20T16:00:00Z"
METRIC_END_DATE = "2025-06-12T16:00:00Z"

# Mapping using your specified slugs
protocol_slugs = {
    "Rocket Pool": "rocket-pool",
    "SuperForm": "superform",
    "Balancer & Beets": ["balancer", "beets"],
    "Avantis": "avantis",
    "Polynomial": "polynomial-protocol",
    "Extra Finance": "extra-finance",
    "Gyroscope": "gyroscope-protocol",
    "Reservoir": "reservoir-protocol",
    "QiDAO": "qidao",
    "Silo": "silo-finance",
    "Exactly": "exactly",
    "Ionic Protocol": "ionic-protocol",
    "Ironclad Finance": "ironclad-finance",
    "Lets Get HAI": "lets-get-hai",
    "Maverick Protocol": "maverick-protocol",
    "Metronome": "metronome",
    "Overnight Finance": "overnight-finance",
    "Peapods Finance": "peapods-finance",
    "Sushi": "sushi",
    "SynFutures": "synfutures",
    "Thales": "thales",
    "TLX Finance": "tlx-finance",
}

def normalize_chain_name(raw_name: str) -> str:
    """Return a consistent name for known synonyms, e.g. 'Optimism' -> 'op mainnet'."""
    lowered = raw_name.lower().strip()
    if lowered == "optimism":
        return "op mainnet"
    return raw_name

# Updated list of chains from the second document
superchain_chains = [
    "bob", "base", "ink", "lisk", "mode", "op mainnet", 
    "polynomial", "soneium", "swellchain", "unichain", "world chain"
]

def fetch_protocol_data(slug: str) -> dict:
    """Fetch protocol data from DeFiLlama API"""
    url = f"https://api.llama.fi/protocol/{slug}"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error fetching data for {slug}: {e}")
        return None

def get_history_list(chain_data):
    """Extract the history list from chain data"""
    if isinstance(chain_data, list):
        return chain_data
    if isinstance(chain_data, dict) and "tvl" in chain_data:
        return chain_data["tvl"]
    return []

def extract_timestamp(entry) -> float:
    """Extract timestamp from an entry"""
    try:
        if isinstance(entry, dict):
            for k in ["date", "t", "timestamp"]:
                if k in entry:
                    return float(entry[k])
        elif isinstance(entry, list) and entry:
            return float(entry[0])
    except Exception:
        pass
    return None

def extract_value(entry) -> float:
    """Extract TVL value from an entry"""
    try:
        return entry['totalLiquidityUSD']
    except Exception:
        pass
    return 0

def extract_history_data(protocol_data: dict, protocol_name: str) -> dict:
    """
    Extract all historical data for a protocol across relevant chains.
    Returns a dictionary mapping chain names to lists of (timestamp, value) pairs.
    """
    if not protocol_data or "chainTvls" not in protocol_data:
        print(f"No chainTvls data for '{protocol_name}'")
        return {}
        
    chain_tvls = protocol_data["chainTvls"]
    # Print all keys found in chainTvls
    print(f"chainTvls keys for '{protocol_name}': {list(chain_tvls.keys())}")

    found_superchain_chains = []
    out = {}
    
    for chain_name, chain_data in chain_tvls.items():
        unified_name = normalize_chain_name(chain_name)
        norm = unified_name.replace(" ", "").lower()

        if any(norm == c.replace(" ", "").lower() for c in superchain_chains):
            hist = []
            history_list = get_history_list(chain_data)
            for entry in history_list:
                ts = extract_timestamp(entry)
                if ts is not None:
                    tvl = extract_value(entry)
                    hist.append((ts, tvl))
            if hist:
                out[unified_name] = sorted(hist, key=lambda x: x[0])
                found_superchain_chains.append(unified_name)

    # Print summary of recognized "superchain" chains
    print(f"Found {len(found_superchain_chains)} superchain chain(s) for '{protocol_name}': {found_superchain_chains}")
    return out

def calculate_average_tvl_in_range(history_entries, start_ts, end_ts):
    """Calculate average TVL within a date range, return None if no data points exist"""
    points = [(ts, v) for ts, v in history_entries if start_ts < ts <= end_ts]
    if not points:
        return None
    assert len(points) <= 7
    return sum(v for _, v in points) / len(points)

def process_protocol(slug: str, protocol_name: str) -> dict:
    """Process a single protocol and extract its history data"""
    data = fetch_protocol_data(slug)
    if not data:
        return {}
    return extract_history_data(data, protocol_name)

def calculate_7day_averages(history_data: dict, target_ts: float) -> float:
    """
    Calculate 7-day averages for all chains in the history data.
    If a chain has no data in the window, skip it rather than failing.
    """
    start_ts = target_ts - 7 * 24 * 60 * 60
    total = 0
    for chain_key, entries in history_data.items():
        avg = calculate_average_tvl_in_range(entries, start_ts, target_ts)
        if avg is None:
            print(f"Warning: Chain '{chain_key}' has no data in the 7-day window near timestamp {target_ts}")
            continue
        total += avg
    return total

def process_protocol_or_slugs(slugs, ts1, ts2, protocol_name: str):
    """
    Process a protocol (which may consist of multiple slugs).
    Returns (avg1, avg2) tuple.
    """
    if isinstance(slugs, list):
        total1, total2 = 0, 0
        for s in slugs:
            hist = process_protocol(s, f"{protocol_name} ({s})")
            if not hist:
                print(f"No history data for '{protocol_name}' slug '{s}'")
                continue
            a1 = calculate_7day_averages(hist, ts1)
            a2 = calculate_7day_averages(hist, ts2)
            total1 += a1
            total2 += a2
        return total1, total2
    else:
        hist = process_protocol(slugs, protocol_name)
        if not hist:
            print(f"No history data for '{protocol_name}'")
            return 0, 0
        a1 = calculate_7day_averages(hist, ts1)
        a2 = calculate_7day_averages(hist, ts2)
        return a1, a2

def main():
    """Main function to process protocols and generate CSV report"""
    d1 = datetime.fromisoformat(METRIC_START_DATE.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(METRIC_END_DATE.replace("Z", "+00:00"))
    now_dt = datetime.now(timezone.utc)
    d2 = min(end_dt, now_dt)  # Use whichever is earlier

    ts1, ts2 = d1.timestamp(), d2.timestamp()
    sd1 = d1.strftime("%b%d_%Y").lower()
    sd2 = d2.strftime("%b%d_%Y").lower()

    out_file = f"protocols_superchain_tvl_{sd1}_to_{sd2}.csv"
    headers = ["protocol", f"7d_avg_tvl_{sd1}", f"7d_avg_tvl_{sd2}", "difference"]

    print(
        f"Processing data with 7-day windows ending at:\n"
        f"  Start Date: {d1}\n  End Date:   {d2}\n"
    )

    try:
        with open(out_file, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            for name, slug_data in protocol_slugs.items():
                print(f"\nProcessing '{name}' ...")
                
                tvl1, tvl2 = process_protocol_or_slugs(slug_data, ts1, ts2, name)
                diff = tvl2 - tvl1
                row = {
                    "protocol": name,
                    f"7d_avg_tvl_{sd1}": round(tvl1),
                    f"7d_avg_tvl_{sd2}": round(tvl2),
                    "difference": round(diff),
                }
                writer.writerow(row)
                print(f"  -> 7d Avg at start={tvl1:.2f}, end={tvl2:.2f}, diff={diff:.2f}")

        print(f"\nCSV '{out_file}' created successfully.\n")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
