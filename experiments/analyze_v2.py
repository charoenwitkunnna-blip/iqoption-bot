#!/usr/bin/env python3
"""Analyze V2 confidence thresholds - find optimal cutoff"""
import sys, os, json, importlib
BASE_DIR = "/root/iqoption-bot/experiments"
sys.path.insert(0, BASE_DIR)

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option
api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("PRACTICE")
import time; time.sleep(1)

spec = importlib.util.spec_from_file_location("v2", f"{BASE_DIR}/v2/strategy.py")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)

# Focus on EURJPY-OTC (best) and a few others
ASSETS = ["EURJPY-OTC", "GBPJPY-OTC", "XAUUSD-OTC", "EURUSD-OTC", "GBPUSD-OTC", "SP500-OTC"]

# Collect all trades with their confidence levels
all_trades = []

for asset in ASSETS:
    candles = api.get_candles(asset, 60, 2000, time.time())
    if not candles or len(candles) < 200:
        continue
    close = [c['close'] for c in candles]
    
    for i in range(200, len(candles)-2):
        window = candles[:i+1]
        try:
            pred = v2.analyze(api, asset, window)
        except:
            continue
        if not pred or not isinstance(pred, (tuple, list)):
            continue
        direction, confidence = pred
        if direction not in ["call", "put"]:
            continue
        
        won = (direction=="call" and close[i+1]>close[i]) or (direction=="put" and close[i+1]<close[i])
        all_trades.append({"asset": asset, "direction": direction, "conf": confidence, "won": won})

print(f"Total trades captured: {len(all_trades)}")

# Analyze by confidence brackets
brackets = [(50,60), (60,70), (70,80), (80,90), (90,100)]
print(f"\n{'Bracket':<12} {'Trades':<10} {'Wins':<8} {'WR':<8}")
print("-"*40)
for lo, hi in brackets:
    subset = [t for t in all_trades if lo <= t['conf'] < hi]
    if not subset:
        continue
    wins = sum(1 for t in subset if t['won'])
    wr = wins/len(subset)*100
    print(f"{lo}-{hi:<5}   {len(subset):<10} {wins:<8} {wr:<8.1f}")

# Analyze by asset
print(f"\n{'Asset':<15} {'Trades':<10} {'Wins':<8} {'WR':<8} {'Avg Conf':<10}")
print("-"*55)
for asset in ASSETS:
    subset = [t for t in all_trades if t['asset'] == asset]
    if not subset:
        continue
    wins = sum(1 for t in subset if t['won'])
    wr = wins/len(subset)*100
    avg_conf = sum(t['conf'] for t in subset)/len(subset)
    print(f"{asset:<15} {len(subset):<10} {wins:<8} {wr:<8.1f} {avg_conf:<10.1f}")

# Best confidence filter
print(f"\n=== FINDING OPTIMAL CONFIDENCE FILTER ===")
print(f"{'Min Conf':<10} {'Trades':<10} {'Wins':<8} {'WR':<8}")
print("-"*40)
for conf_thresh in range(50, 100, 5):
    subset = [t for t in all_trades if t['conf'] >= conf_thresh]
    if len(subset) < 3:
        continue
    wins = sum(1 for t in subset if t['won'])
    wr = wins/len(subset)*100
    print(f"{conf_thresh:<10} {len(subset):<10} {wins:<8} {wr:<8.1f}")
