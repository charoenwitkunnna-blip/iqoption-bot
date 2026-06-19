#!/usr/bin/env python3
"""
ML DATA COLLECTOR — pulls 1-min candles for all paying assets.
Saves raw data to experiments/ml_data/ for training.
Run this first, then ml_train.py overnight.
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(__file__))

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

DATA_DIR = "/root/iqoption-bot/experiments/ml_data"
os.makedirs(DATA_DIR, exist_ok=True)

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("PRACTICE")
time.sleep(2)

# Get all paying assets
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

# Pull candles for each asset
total_candles = 0
for i, asset in enumerate(assets):
    try:
        # Pull up to 1000 1-min candles
        candles = api.get_candles(asset, 60, 1000, time.time())
        if not candles or len(candles) < 100:
            print(f"  [{i+1}/{len(assets)}] {asset}: {len(candles) if candles else 0} candles — SKIP (too few)")
            continue

        # Clean: keep only needed fields
        clean = []
        for c in candles:
            clean.append({
                'open': c['open'],
                'close': c['close'],
                'max': c['max'],
                'min': c['min'],
                'time': c.get('from', c.get('time', 0))
            })

        fname = asset.replace('/', '_').replace(' ', '_')
        path = os.path.join(DATA_DIR, f"{fname}.json")
        with open(path, 'w') as f:
            json.dump(clean, f)

        total_candles += len(clean)
        print(f"  [{i+1}/{len(assets)}] {asset}: {len(clean)} candles ✓")
        time.sleep(0.3)  # Rate limit

    except Exception as e:
        print(f"  [{i+1}/{len(assets)}] {asset}: ERROR — {e}")

api.close_connect()
print(f"\nDone. {total_candles} total candles across {len(os.listdir(DATA_DIR))} assets.")
print(f"Data saved to {DATA_DIR}/")
