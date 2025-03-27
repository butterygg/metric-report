import csv
from datetime import datetime, timezone

import requests

METRIC_START_DATE = "2025-03-20T16:00:00Z"
METRIC_END_DATE = "2025-06-12T16:00:00Z"

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


superchain_chains = [
    "bob",
    "base",
    "ink",
    "lisk",
    "mode",
    "op mainnet",
    "polynomial",
    "soneium",
    "swellchain",
    "unichain",
    "world chain",
]


def fetch_protocol_data(slug: str) -> dict:
    url = f"https://api.llama.fi/protocol/{slug}"
    r = requests.get(url)  # optionally: requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def get_history_list(chain_data):
    if isinstance(chain_data, list):
        return chain_data
    if isinstance(chain_data, dict) and "tvl" in chain_data:
        return chain_data["tvl"]
    return []


def extract_timestamp(entry) -> float:
    if isinstance(entry, dict):
        for k in ["date", "t", "timestamp"]:
            if k in entry:
                return float(entry[k])
    elif isinstance(entry, list) and entry:
        return float(entry[0])
    raise ValueError(f"Cannot find timestamp in entry: {entry}")


def extract_value(entry) -> float:
    if isinstance(entry, dict):
        for k in ["totalLiquidityUSD", "v", "value", "tvl"]:
            if k in entry:
                return float(entry[k])
    elif isinstance(entry, list) and len(entry) > 1:
        return float(entry[1])
    raise ValueError(f"Cannot find TVL value in entry: {entry}")


def extract_history_data(protocol_data: dict, protocol_name: str) -> dict:
    chain_tvls = protocol_data["chainTvls"]
    # Print *all* keys found in chainTvls
    print(f"chainTvls keys for '{protocol_name}': {list(chain_tvls.keys())}")

    found_superchain_chains = []
    out = {}
    for chain_name, chain_data in chain_tvls.items():
        unified_name = normalize_chain_name(chain_name)
        norm = unified_name.replace(" ", "").lower()

        if any(norm == c.replace(" ", "").lower() for c in superchain_chains):
            hist = []
            for entry in get_history_list(chain_data):
                ts = extract_timestamp(entry)
                tvl = extract_value(entry)
                hist.append((ts, tvl))
            if hist:
                out[unified_name] = sorted(hist, key=lambda x: x[0])
                found_superchain_chains.append(unified_name)

    # Print summary of recognized “superchain” chains (if any)
    print(
        f"Found {len(found_superchain_chains)} superchain chain(s) for '{protocol_name}': {found_superchain_chains}"
    )
    return out


def calculate_average_tvl_in_range(history_entries, start_ts, end_ts):
    points = [(ts, v) for ts, v in history_entries if start_ts <= ts <= end_ts]
    if not points:
        return None
    return sum(v for _, v in points) / len(points)


def process_protocol(slug: str, protocol_name: str) -> dict:
    data = fetch_protocol_data(slug)
    return extract_history_data(data, protocol_name)


def calculate_7day_averages(history_data: dict, target_ts: float) -> float:
    start_ts = target_ts - 7 * 24 * 60 * 60
    total = 0
    for chain_key, entries in history_data.items():
        avg = calculate_average_tvl_in_range(entries, start_ts, target_ts)
        if avg is None:
            raise ValueError(
                f"Chain '{chain_key}' has no data in the 7-day window near timestamp {target_ts}"
            )
        total += avg
    return total


def process_protocol_or_slugs(slugs, ts1, ts2, protocol_name: str):
    if isinstance(slugs, list):
        total1, total2 = 0, 0
        for s in slugs:
            hist = process_protocol(s, protocol_name)
            a1 = calculate_7day_averages(hist, ts1)
            a2 = calculate_7day_averages(hist, ts2)
            total1 += a1
            total2 += a2
        return total1, total2
    else:
        hist = process_protocol(slugs, protocol_name)
        a1 = calculate_7day_averages(hist, ts1)
        a2 = calculate_7day_averages(hist, ts2)
        return a1, a2


def main():
    d1 = datetime.fromisoformat(METRIC_START_DATE.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(METRIC_END_DATE.replace("Z", "+00:00"))
    now_dt = datetime.now(timezone.utc)
    d2 = min(end_dt, now_dt)  # whichever is earlier

    ts1, ts2 = d1.timestamp(), d2.timestamp()
    sd1 = d1.strftime("%b%d_%Y").lower()
    sd2 = d2.strftime("%b%d_%Y").lower()

    out_file = f"protocols_superchain_tvl_{sd1}_to_{sd2}.csv"
    headers = ["protocol", f"7d_avg_tvl_{sd1}", f"7d_avg_tvl_{sd2}", "difference"]

    print(
        f"Processing data with 7-day windows ending at:\n"
        f"  Start Date: {d1}\n  End Date:   {d2}\n"
    )

    with open(out_file, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        for name, slug_data in protocol_slugs.items():
            print(f"\nProcessing '{name}' ...")
            tvl1, tvl2 = process_protocol_or_slugs(slug_data, ts1, ts2, name)
            if tvl1 is None or tvl2 is None:
                raise ValueError(f"No 7-day data for '{name}' at times {ts1} or {ts2}")
            diff = tvl2 - tvl1
            writer.writerow(
                {
                    "protocol": name,
                    f"7d_avg_tvl_{sd1}": tvl1,
                    f"7d_avg_tvl_{sd2}": tvl2,
                    "difference": diff,
                }
            )
            print(f"  -> 7d Avg at start={tvl1:.2f}, end={tvl2:.2f}, diff={diff:.2f}")

    print(f"\nCSV '{out_file}' created successfully.\n")


if __name__ == "__main__":
    main()
