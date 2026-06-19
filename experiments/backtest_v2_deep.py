#!/usr/bin/env python3
"""Deep backtest V2 strategy - 1500+ candles, verify 70% win rate"""
import sys, os, time, json, importlib
import pandas as pd
import numpy as np

BASE_DIR = "/root/iqoption-bot/experiments"
sys.path.insert(0, BASE_DIR)

print("Connecting...")
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option
api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("PRACTICE")
time.sleep(1)

spec = importlib.util.spec_from_file_location("v2", f"{BASE_DIR}/v2/strategy.py")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)

# Test on 8 major assets with 1500 candles each
ASSETS = ["EURUSD-OTC", "GBPUSD-OTC", "SP500-OTC", "XAUUSD-OTC", 
          "GBPJPY-OTC", "AUDUSD-OTC", "USDJPY-OTC", "EURJPY-OTC"]

all_results = {}

for asset in ASSETS:
    print(f"\n{asset}: fetching 1500 candles...", end=" ", flush=True)
    candles = api.get_candles(asset, 60, 1500, time.time())
    if not candles or len(candles) < 200:
        print("SKIP (not enough)")
        continue
    
    close = [c['close'] for c in candles]
    
    wins, losses = 0, 0
    correct = []  # For confidence trend
    
    for i in range(150, len(candles) - 2):
        window = candles[:i+1]  # Use data up to current candle
        
        try:
            pred = v2.analyze(api, asset, window)
        except:
            continue
        
        if isinstance(pred, (tuple, list)):
            pred = pred[0]
        if pred not in ["call", "put"]:
            continue
        
        curr = close[i]
        nxt = close[i+1]
        
        result = (pred == "call" and nxt > curr) or (pred == "put" and nxt < curr)
        if result:
            wins += 1
            correct.append(1)
        else:
            losses += 1
            correct.append(0)
    
    total = wins + losses
    wr = (wins / total * 100) if total > 0 else 0
    all_results[asset] = {"sigs": total, "wins": wins, "losses": losses, "wr": round(wr, 1)}
    
    # Streak analysis
    streak_str = "".join("W" if c else "L" for c in correct[-40:])
    print(f"{total} sigs, {wr:.1f}% wr | streak: ...{streak_str}")

print(f"\n{'='*60}")
print(f"{'ASSET':<20} {'SIGS':<8} {'WINS':<8} {'LOSSES':<8} {'WR':<8}")
print(f"{'='*60}")
total_s, total_w, total_l = 0, 0, 0
for asset, r in all_results.items():
    print(f"{asset:<20} {r['sigs']:<8} {r['wins']:<8} {r['losses']:<8} {r['wr']:<8}")
    total_s += r['sigs']
    total_w += r['wins']
    total_l += r['losses']
wr = (total_w / total_s * 100) if total_s > 0 else 0
print(f"{'='*60}")
print(f"{'TOTAL':<20} {total_s:<8} {total_w:<8} {total_l:<8} {wr:<8.1f}")

with open(f"{BASE_DIR}/results/v2_backtest_deep.json", "w") as f:
    json.dump(all_results, f, indent=2)

# Additional test: check if streaks suggest non-randomness
if total_s > 20:
    from scipy import stats
    z = (wr/100 - 0.5) / (0.5 / (total_s**0.5))
    print(f"\nStatistical significance: z={z:.2f}, p={stats.norm.sf(abs(z))*2:.4f}")
