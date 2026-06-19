#!/usr/bin/env python3
"""VALID backtest: ALL 7 strategies on same candles. Signal on 0..N-1, outcome on N."""
import sys, os, time, importlib, warnings, inspect
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(__file__))

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option
warnings.filterwarnings("ignore")

STRAT_NAMES = [
    "alpha_momentum", "beta_reversal", "gamma_breakout",
    "delta_squeeze", "epsilon_divergence", "zeta_heikinashi",
    "replica_exact"
]

mods = {}
for name in STRAT_NAMES:
    if name == "replica_exact":
        mod = importlib.import_module(f"{name}.strategy")
    else:
        mod = importlib.import_module(f"new_algos.{name}.strategy")
    sig = inspect.signature(mod.analyze)
    mods[name] = (mod, len(sig.parameters) > 3)

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
        if p and p > 0: paying[asset] = p
    except: pass

all_paying = sorted(paying, key=paying.get, reverse=True)

results = {n: {"w": 0, "l": 0, "pnl": 0.0} for n in STRAT_NAMES}

for asset in all_paying:
    try:
        candles = api.get_candles(asset, 60, 60, time.time())
        if not candles or len(candles) < 35: continue
    except: continue

    payout = paying.get(asset, 0.87)

    htf_candles = None
    try:
        htf_candles = api.get_candles(asset, 300, 30, time.time())
    except: pass

    signal_candles = candles[:-1]
    entry_open = candles[-2]['close']
    outcome_close = candles[-1]['close']

    for name, (mod, needs_htf) in mods.items():
        try:
            if needs_htf:
                direction, conf = mod.analyze(api, asset, signal_candles, htf_candles)
            else:
                direction, conf = mod.analyze(api, asset, signal_candles)
        except: continue

        if direction is None: continue

        win = (outcome_close > entry_open) if direction == "call" else (outcome_close < entry_open)
        pnl = payout if win else -1.0
        if win: results[name]["w"] += 1
        else: results[name]["l"] += 1
        results[name]["pnl"] += pnl

    time.sleep(0.2)

print(f"{'Strategy':<22s} {'W':>4s} {'L':>4s} {'Sig':>4s} {'WR':>6s} {'PnL':>8s}  Verdict")
print("-" * 62)
ranked = sorted(results.items(), key=lambda x: x[1]['pnl'], reverse=True)
for name, r in ranked:
    t = r["w"] + r["l"]
    if t > 0:
        wr = f"{r['w']/t*100:.0f}%"
        if r['w']/t >= 0.58: v = "STRONG"
        elif r['w']/t >= 0.54: v = "GOOD"
        elif r['w']/t >= 0.50: v = "OK"
        else: v = "WEAK"
    else:
        wr = "N/A"; v = "DEAD"
    print(f"{name:<22s} {r['w']:>4d} {r['l']:>4d} {t:>4d} {wr:>6s} {r['pnl']:>+8.2f}  {v}")

print()
best = ranked[0]
t = best[1]['w'] + best[1]['l']
if t > 0:
    print(f">>> #1: {best[0]} — {best[1]['w']}/{t} = {best[1]['w']/t*100:.0f}% wr, pnl={best[1]['pnl']:+.2f}")
