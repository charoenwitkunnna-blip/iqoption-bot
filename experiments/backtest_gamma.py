#!/usr/bin/env python3
"""Deep backtest: gamma_breakout on ALL paying assets across multiple snapshots."""
import sys, os, time, importlib, warnings, inspect
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(__file__))

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option
warnings.filterwarnings("ignore")

mod = importlib.import_module("new_algos.gamma_breakout.strategy")

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("PRACTICE")
time.sleep(2)

all_a = api.get_all_open_time()
all_pairs = {x: v for x, v in all_a['turbo'].items() if v['open']}

paying = {}
for asset in list(all_pairs.keys()):
    try:
        p = api.get_digital_payout(asset)
        if p and p > 0:
            paying[asset] = p
    except:
        pass

all_paying = sorted(paying, key=paying.get, reverse=True)
print(f"Running gamma_breakout on {len(all_paying)} assets...")

total_wins = 0
total_losses = 0
total_signals = 0
by_asset = {}

for asset in all_paying:
    try:
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 30:
            continue
    except:
        continue

    payout = paying.get(asset, 0.87)

    try:
        direction, confidence = mod.analyze(api, asset, candles)
    except:
        continue

    if direction is None:
        continue

    total_signals += 1

    # Outcome: simulate on last completed candle
    if len(candles) > 1:
        last_open = candles[-2]['close']
        last_close = candles[-1]['close']
    else:
        last_open = candles[-1]['open']
        last_close = candles[-1]['close']

    if direction == "call":
        win = last_close > last_open
    else:
        win = last_close < last_open

    by_asset.setdefault(asset, {"w": 0, "l": 0})
    if win:
        total_wins += 1
        by_asset[asset]["w"] += 1
        print(f"  {asset:20s} {direction:5s} WIN  (conf={confidence})")
    else:
        total_losses += 1
        by_asset[asset]["l"] += 1
        print(f"  {asset:20s} {direction:5s} LOSS (conf={confidence})")

    time.sleep(0.2)

print()
total = total_wins + total_losses
wr = total_wins/total*100 if total else 0
pnl_per_trade = paying.get(asset, 0.87)  # approximate
total_pnl = total_wins * pnl_per_trade - total_losses
print(f"=== GAMMA BREAKOUT: {total_wins}/{total} = {wr:.0f}% wr, pnl={total_pnl:+.2f} ===")

# Top performing assets
print("\nTop assets:")
for a, d in sorted(by_asset.items(), key=lambda x: x[1]['w'] - x[1]['l'], reverse=True)[:5]:
    t = d['w'] + d['l']
    print(f"  {a}: {d['w']}/{t} = {d['w']/t*100:.0f}%")

api.close_connect()
