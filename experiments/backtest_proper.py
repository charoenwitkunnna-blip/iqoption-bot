#!/usr/bin/env python3
"""VALID backtest — signal on candles[:-1], outcome on last candle."""
import sys, os, time, importlib, warnings, inspect, copy
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(__file__))

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option
warnings.filterwarnings("ignore")

# Load strategies
mods = {}
for name in ["alpha_momentum", "beta_reversal", "gamma_breakout", "replica_exact"]:
    if name == "replica_exact":
        mods[name] = importlib.import_module(f"{name}.strategy")
    else:
        mods[name] = importlib.import_module(f"new_algos.{name}.strategy")
    sig = inspect.signature(mods[name].analyze)
    mods[name] = (mods[name], len(sig.parameters) > 3)

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

results = {n: {"w": 0, "l": 0, "pnl": 0.0} for n in mods}

for asset in all_paying:
    try:
        candles = api.get_candles(asset, 60, 60, time.time())
        if not candles or len(candles) < 35:
            continue
    except:
        continue

    payout = paying.get(asset, 0.87)

    # Get HTF candles
    htf_candles = None
    try:
        htf_candles = api.get_candles(asset, 300, 30, time.time())
    except:
        pass

    # === VALID BACKTEST ===
    # Signal uses candles[0:-2] (all EXCEPT last completed candle)
    # Outcome is candles[-2] -> candles[-1] (the "future" candle)
    signal_candles = candles[:-1]  # exclude the very last which we test against
    entry_open = candles[-2]['close']   # open of outcome candle
    outcome_close = candles[-1]['close']  # close of outcome candle

    for name, (mod, needs_htf) in mods.items():
        try:
            if needs_htf:
                direction, conf = mod.analyze(api, asset, signal_candles, htf_candles)
            else:
                direction, conf = mod.analyze(api, asset, signal_candles)
        except:
            continue

        if direction is None:
            continue

        if direction == "call":
            win = outcome_close > entry_open
        else:
            win = outcome_close < entry_open

        pnl = payout if win else -1.0
        if win:
            results[name]["w"] += 1
        else:
            results[name]["l"] += 1
        results[name]["pnl"] += pnl

    time.sleep(0.2)

# Summary
print(f"{'Strategy':<20s} {'W':>4s} {'L':>4s} {'WR':>6s} {'PnL':>8s}")
print("-" * 48)
for name in mods:
    r = results[name]
    t = r["w"] + r["l"]
    if t > 0:
        wr = f"{r['w']/t*100:.0f}%"
    else:
        wr = "N/A"
    print(f"{name:<20s} {r['w']:>4d} {r['l']:>4d} {wr:>6s} {r['pnl']:>+8.2f}")

api.close_connect()
