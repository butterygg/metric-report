#!/usr/bin/env python3
import requests
import json
import sys
from datetime import datetime, timedelta
from statistics import mean

def calculate_unichain_30day_average(protocol_slug):
    """Calculate 30-day trailing average for a protocol on Unichain (TVL + Borrowed)"""
    
    # Fetch protocol data
    protocol_url = f"https://api.llama.fi/protocol/{protocol_slug}"
    print(f"Fetching {protocol_slug} data...")
    response = requests.get(protocol_url)
    
    if response.status_code != 200:
        print(f"Error: Failed to fetch protocol data (HTTP {response.status_code})")
        return None
    
    data = response.json()
    
    if 'chainTvls' not in data:
        print("Error: No chain TVL data found")
        return None
    
    # Get Unichain TVL data
    unichain_tvl_data = data['chainTvls'].get('Unichain', {}).get('tvl', [])
    
    # Get Unichain Borrowed data (separate chain entry)
    unichain_borrowed_data = data['chainTvls'].get('Unichain-borrowed', {}).get('tvl', [])
    
    print(f"Unichain TVL data points: {len(unichain_tvl_data)}")
    print(f"Unichain-borrowed data points: {len(unichain_borrowed_data)}")
    
    # Target date range: 30 days ending on 2025-08-10
    end_date = datetime(2025, 8, 10)
    start_date = end_date - timedelta(days=29)  # 30 days total
    
    print(f"\nProcessing data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Process TVL data
    tvl_by_date = {}
    for point in unichain_tvl_data:
        if 'date' in point:
            date = datetime.fromtimestamp(point['date'])
            # Compare just the date part, not the time
            if start_date.date() <= date.date() <= end_date.date():
                date_str = date.strftime('%Y-%m-%d')
                tvl_by_date[date_str] = point.get('totalLiquidityUSD', 0)
    
    # Process borrowed data
    borrowed_by_date = {}
    for point in unichain_borrowed_data:
        if 'date' in point:
            date = datetime.fromtimestamp(point['date'])
            # Compare just the date part, not the time
            if start_date.date() <= date.date() <= end_date.date():
                date_str = date.strftime('%Y-%m-%d')
                borrowed_by_date[date_str] = point.get('totalLiquidityUSD', 0)
    
    print(f"\nFound TVL data for {len(tvl_by_date)} days")
    print(f"Found Borrowed data for {len(borrowed_by_date)} days")
    
    # Calculate daily totals (TVL + Borrowed)
    daily_totals = []
    print("\nDaily breakdown:")
    days_with_data = 0
    for day_num in range(30):
        current_date = start_date + timedelta(days=day_num)
        date_str = current_date.strftime('%Y-%m-%d')
        
        tvl = tvl_by_date.get(date_str, 0)
        borrowed = borrowed_by_date.get(date_str, 0)
        total = tvl + borrowed
        
        if tvl > 0 or borrowed > 0:  # Only show days with data
            print(f"{date_str}: TVL=${tvl:,.2f} + Borrowed=${borrowed:,.2f} = ${total:,.2f}")
            days_with_data += 1
        
        daily_totals.append(total)
    
    print(f"\nTotal days in calculation: 30")
    print(f"Days with actual data: {days_with_data}")
    print(f"Days with zero/missing data: {30 - days_with_data}")
    
    # Calculate 30-day trailing average
    if daily_totals:
        avg = mean(daily_totals)
        result = int(avg)  # Round down to nearest integer
        
        print(f"\n" + "="*60)
        print(f"30-day trailing average: ${avg:,.2f}")
        print(f"Rounded DOWN to nearest integer: ${result:,}")
        print("="*60)
        
        return result
    else:
        print("No data available for calculation")
        return None

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python venus_final_calculation.py <protocol-slug>")
        print("Example: python venus_final_calculation.py venus-core-pool")
        sys.exit(1)
    
    protocol_slug = sys.argv[1]
    print(f"=== {protocol_slug} Unichain 30-Day Trailing Average ===\n")
    
    result = calculate_unichain_30day_average(protocol_slug)
    
    if result is not None:
        print(f"\n" + "="*60)
        print(f"FINAL ANSWER: {result}")
        print("="*60)
    else:
        sys.exit(1)