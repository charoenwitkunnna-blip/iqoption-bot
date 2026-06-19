#!/usr/bin/env python3
"""Head-to-head: sigma_reversion vs gamma_breakout on same candles."""
import sys, os, time, importlib, warnings
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(__file__))

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option
warnings.filterwarnings("ignore")

gamma = importlib.import_module("new_algos.gamma_breakout.strategy")
sigma = importlib.import_module("new_algos.sigma_reversion.strategy")

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
        if p and p >= 85: paying[asset] = p
    except: pass

all_paying = sorted(paying, key=paying.get, reverse=True)

results = {"gamma": {"w": 0, "l": 0}, "sigma": {"w": 0, "l": 0}}

for asset in all_paying:
    try:
        candles = api.get_candles(asset, 60, 60, time.time())
        if not candles or len(candles) < 35: continue
    except: continue

    payout = paying.get(asset, 0.87)
    signal_candles = candles[:-1]
    entry_open = candles[-2]['close']
    outcome_close = candles[-1]['close']

    for name, strat in [("gamma", gamma), ("sigma", sigma)]:
        try:
            direction, conf = strat.analyze(api, asset, signal_candles)
        except: continue
        if direction is None: continue

        win = (outcome_close > entry_open) if direction == "call" else (outcome_close < entry_open)
        if win: results[name]["w"] += 1
        else: results[name]["l"] += 1

    time.sleep(0.2)

print(f"{'Strategy':<20s} {'W':>4s} {'L':>4s} {'Sig':>4s} {'WR':>6s}  Verdict")
print("-" * 50)
for name in ["gamma", "sigma"]:
    r = results[name]; t = r["w"] + r["l"]
    if t > 0:
        wr = f"{r['w']/t*100:.0f}%"
        v = "STRONG" if r['w']/t >= 0.58 else ("GOOD" if r['w']/t >= 0.54 else ("OK" if r['w']/t >= 0.50 else "WEAK"))
    else:
        wr = "N/A"; v = "DEAD"
    print(f"{name:<20s} {r['w']:>4d} {r['l']:>4d} {t:>4d} {wr:>6s}  {v}")
