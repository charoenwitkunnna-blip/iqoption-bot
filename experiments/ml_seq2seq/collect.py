#!/usr/bin/env python3
"""
ML SEQ2SEQ DATA COLLECTOR — pulls 5-second candles for all paying assets.
Collects enough data to train the 50→20 candle prediction model.
Saves to data/ as asset files + one consolidated numpy file.

Usage: source ../../venv/bin/activate && python3 collect.py
"""
import sys, os, time, json
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

ASSET_CANDLES = 5000    # How many 5-sec candles to pull per asset

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("PRACTICE")
time.sleep(2)

# Find all open assets with decent payout
all_a = api.get_all_open_time()
pairs = {x: v for x, v in all_a['turbo'].items() if v['open']}
paying = {}
for a in list(pairs.keys()):
    try:
        p = api.get_digital_payout(a)
        if p and p >= 80:
            paying[a] = p
    except:
        pass

assets = sorted(paying, key=paying.get, reverse=True)
print(f"Found {len(assets)} paying assets (payout >= 80%)")

total_candles = 0
for i, asset in enumerate(assets):
    try:
        # Pull 5-second candles
        candles = api.get_candles(asset, 5, ASSET_CANDLES, time.time())
        if not candles or len(candles) < 200:
            print(f"  [{i+1}/{len(assets)}] {asset}: {len(candles) if candles else 0} — SKIP (too few)")
            continue

        # Sort by time so they're in order
        candles.sort(key=lambda c: c.get('from', c.get('time', 0)))

        clean = []
        for c in candles:
            clean.append({
                'open': c['open'],
                'high': c['max'],
                'low': c['min'],
                'close': c['close'],
                'time': c.get('from', c.get('time', 0))
            })

        fname = asset.replace('/', '_').replace(' ', '_')
        path = os.path.join(DATA_DIR, f"{fname}.json")
        with open(path, 'w') as f:
            json.dump(clean, f)

        total_candles += len(clean)
        print(f"  [{i+1}/{len(assets)}] {asset}: {len(clean)} candles")
        # Small delay to avoid rate limiting
        time.sleep(0.4)

    except Exception as e:
        print(f"  [{i+1}/{len(assets)}] {asset}: ERROR — {e}")
        time.sleep(1)

api.close_connect()

# Also write a meta file
meta = {
    "asset_count": len([f for f in os.listdir(DATA_DIR) if f.endswith('.json')]),
    "total_candles": total_candles,
    "candle_seconds": 5,
    "assets": assets[:20]  # Top 20 for reference
}
with open(os.path.join(DATA_DIR, "_meta.json"), 'w') as f:
    json.dump(meta, f, indent=2)
print(f"\nDone! {total_candles} total 5-sec candles across {meta['asset_count']} assets.")
print(f"Data saved to {DATA_DIR}/")
