#!/usr/bin/env python3
"""Backtest ALL strategies on same candles."""
import sys, os, time, importlib, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(__file__))
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option
warnings.filterwarnings("ignore")

strategies = {
    "gamma":        importlib.import_module("new_algos.gamma_breakout.strategy"),
    "apex":         importlib.import_module("new_algos.apex_ensemble.strategy"),
    "theta_rsi2":   importlib.import_module("new_algos.theta_rsi2.strategy"),
    "omega":        importlib.import_module("new_algos.omega_momentum.strategy"),
    "sigma":        importlib.import_module("new_algos.sigma_reversion.strategy"),
}

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect(); api.change_balance("PRACTICE"); time.sleep(2)

all_a = api.get_all_open_time()
pairs = {x:v for x,v in all_a['turbo'].items() if v['open']}
paying = {}
for a in list(pairs.keys()):
    try:
        p = api.get_digital_payout(a)
        if p and p>=85: paying[a]=p
    except: pass

assets = sorted(paying, key=paying.get, reverse=True)
results = {n: {"w":0,"l":0} for n in strategies}

for asset in assets:
    try:
        c = api.get_candles(asset, 60, 60, time.time())
        if not c or len(c) < 35: continue
    except: continue

    sc = c[:-1]; eo = c[-2]['close']; oc = c[-1]['close']

    for name, strat in strategies.items():
        try: direction, _ = strat.analyze(api, asset, sc)
        except: continue
        if direction is None: continue
        win = (oc > eo) if direction == "call" else (oc < eo)
        if win: results[name]["w"] += 1
        else: results[name]["l"] += 1
    time.sleep(0.12)

print(f"{'Strategy':<16s} {'W':>4s} {'L':>4s} {'Sig':>4s} {'WR':>6s}")
print("-" * 40)
for n, r in sorted(results.items(), key=lambda x: (x[1]['w']/(x[1]['w']+x[1]['l'])) if (x[1]['w']+x[1]['l'])>0 else 0, reverse=True):
    t=r["w"]+r["l"]
    wr=f"{r['w']/t*100:.0f}%" if t>0 else "N/A"
    print(f"{n:<16s} {r['w']:>4d} {r['l']:>4d} {t:>4d} {wr:>6s}")
