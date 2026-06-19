#!/usr/bin/env python3
"""Head-to-head backtest of ALL strategies on the same candle data."""
import sys, os, time, json, importlib, warnings, inspect
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option
warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(__file__))

# Load all strategies
STRATEGIES = {}
for strat_name in ["alpha_momentum", "beta_reversal", "gamma_breakout", "replica_exact"]:
    if strat_name == "replica_exact":
        mod = importlib.import_module(f"{strat_name}.strategy")
    else:
        mod = importlib.import_module(f"new_algos.{strat_name}.strategy")
    sig = inspect.signature(mod.analyze)
    STRATEGIES[strat_name] = {"mod": mod, "needs_htf": len(sig.parameters) > 3}

print("=== STRATEGY BACKTEST: HEAD-TO-HEAD ===")
print(f"Testing {len(STRATEGIES)} strategies")
for n, s in STRATEGIES.items():
    print(f"  {n}: needs_htf={s['needs_htf']}")
print()

# Connect
api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("PRACTICE")
time.sleep(2)

# Get ALL paying assets (not just top 6)
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

top_assets = sorted(paying, key=paying.get, reverse=True)[:15]
print(f"Testing on {len(top_assets)} assets\n")

results = {}
for name in STRATEGIES:
    results[name] = {"signals": 0, "wins": 0, "losses": 0, "pnl": 0.0, "by_asset": {}}

for asset in top_assets:
    # Get LTF candles
    try:
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 30:
            continue
    except:
        continue

    # Get HTF candles (needed by some strategies)
    htf_candles = None
    try:
        htf_candles = api.get_candles(asset, 300, 30, time.time())
    except:
        pass

    payout = paying.get(asset, 0.87)
    asset_signals = 0

    for name, sdata in STRATEGIES.items():
        strat = sdata["mod"]
        needs_htf = sdata["needs_htf"]

        try:
            if needs_htf:
                direction, confidence = strat.analyze(api, asset, candles, htf_candles)
            else:
                direction, confidence = strat.analyze(api, asset, candles)
        except Exception as e:
            continue

        if direction is None:
            continue

        results[name]["signals"] += 1
        asset_signals += 1

        # Simulate trade outcome
        if len(candles) > 1:
            last_open = candles[-2]['close']  # actual last completed candle
            last_close = candles[-1]['close']
        else:
            last_open = candles[-1]['open']
            last_close = candles[-1]['close']

        if direction == "call":
            win = last_close > last_open
        else:
            win = last_close < last_open

        pnl = payout if win else -1.0
        if win:
            results[name]["wins"] += 1
        else:
            results[name]["losses"] += 1
        results[name]["pnl"] += pnl

        results[name].setdefault("by_asset", {})
        results[name]["by_asset"].setdefault(asset, {"w": 0, "l": 0})
        if win:
            results[name]["by_asset"][asset]["w"] += 1
        else:
            results[name]["by_asset"][asset]["l"] += 1

    time.sleep(0.3)

# Summary
print("=" * 75)
print(f"{'Strategy':<20s} {'Sig':>4s} {'W':>3s} {'L':>3s} {'WR':>6s} {'PnL':>8s}  Assessment")
print("-" * 75)

best_name = None
best_pnl = -999
for name in STRATEGIES:
    r = results[name]
    sig = r["signals"]
    w = r["wins"]
    l = r["losses"]
    pnl = r["pnl"]
    if sig > 0:
        wr = f"{w/sig*100:.0f}%"
        assess = "STRONG" if w/sig >= 0.55 else ("OK" if w/sig >= 0.50 else "WEAK")
    else:
        wr = "N/A"
        assess = "NO SIGS"
    print(f"{name:<20s} {sig:>4d} {w:>3d} {l:>3d} {wr:>6s} {pnl:>+8.2f}  {assess}")
    if sig > 0 and pnl > best_pnl:
        best_pnl = pnl
        best_name = name

print()
if best_name:
    r = results[best_name]
    wr = r["wins"]/r["signals"]*100 if r["signals"] else 0
    print(f">>> WINNER: {best_name}  ({r['wins']}/{r['signals']} = {wr:.0f}% wr, pnl={r['pnl']:+.2f})")

    # Show best assets for winner
    ba = r.get("by_asset", {})
    if ba:
        print("   Best assets:")
        for a, d in sorted(ba.items(), key=lambda x: x[1]['w'] - x[1]['l'], reverse=True)[:3]:
            total = d['w'] + d['l']
            if total > 0:
                print(f"     {a}: {d['w']}/{total} = {d['w']/total*100:.0f}%")
else:
    print("No signals from any strategy — market is flat.")

try:
    api.close_connect()
except:
    pass
