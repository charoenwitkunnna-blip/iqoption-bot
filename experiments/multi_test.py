#!/usr/bin/env python3
"""PRACTICE — Test ALL strategies live, one trade each per cycle."""
import sys, os, time, json, importlib

AMOUNT = 5  # Small test amount
BASE_DIR = "/root/iqoption-bot/experiments"
RESULTS_DIR = os.path.join(BASE_DIR, "results")
LOG_FILE = os.path.join(RESULTS_DIR, "multi_test.log")
TRADES_FILE = os.path.join(RESULTS_DIR, "multi_test_trades.json")

sys.path.insert(0, BASE_DIR)
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

STRATEGIES = {
    "gamma":     importlib.import_module("new_algos.gamma_breakout.strategy"),
    "apex":      importlib.import_module("new_algos.apex_ensemble.strategy"),
    "theta_rsi2":importlib.import_module("new_algos.theta_rsi2.strategy"),
    "omega":     importlib.import_module("new_algos.omega_momentum.strategy"),
    "zeta":      importlib.import_module("new_algos.zeta_hybrid.strategy"),
    "eta":       importlib.import_module("new_algos.eta_momentum.strategy"),
}

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

trades = json.load(open(TRADES_FILE)) if os.path.exists(TRADES_FILE) else []

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("PRACTICE")
time.sleep(2)
balance = api.get_balance()

# Get paying assets
all_a = api.get_all_open_time()
all_pairs = {x: v for x, v in all_a['turbo'].items() if v['open']}
paying = {}
for asset in list(all_pairs.keys()):
    try:
        p = api.get_digital_payout(asset)
        if p and p >= 85: paying[asset] = p
    except: pass

top = sorted(paying, key=paying.get, reverse=True)

# Scan all assets, let each strategy vote on each
signals = {name: None for name in STRATEGIES}

for asset in top:
    try:
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 30: continue
    except: continue

    for name, strat in STRATEGIES.items():
        if signals[name] is not None: continue  # Already has signal
        try:
            direction, confidence = strat.analyze(api, asset, candles)
        except: continue
        if direction is None: continue

        # Place trade for this strategy
        try:
            ok, tid = api.buy(AMOUNT, asset, direction, 1)
            if not ok:
                log(f"  {name}: {asset} {direction} FAIL")
                continue
        except: continue

        # Wait for result
        time.sleep(65)
        try:         result = api.check_win_digital_v2(tid)
        if isinstance(result, (list, tuple)):
            win = bool(result[0])
        else:
            win = bool(result)
        except: win = False

        payout_pct = paying.get(asset, 87)
        profit = AMOUNT * (payout_pct / 100) if win else -AMOUNT
        trade = {
            "time": time.strftime('%Y-%m-%d %H:%M:%S'),
            "strategy": name, "asset": asset, "direction": direction,
            "amount": AMOUNT, "confidence": confidence,
            "profit": profit, "win": win
        }
        trades.append(trade)
        json.dump(trades, open(TRADES_FILE, "w"), indent=2)

        # Show per-strategy stats
        strat_trades = [t for t in trades if t['strategy'] == name]
        w = sum(1 for t in strat_trades if t['win'])
        t = len(strat_trades)
        pnl = sum(t['profit'] for t in strat_trades)
        log(f"  {name}: {asset} {direction.upper()} {'WIN' if win else 'LOSS'} | {w}/{t}={w/t*100:.0f}% pnl={pnl:+.1f}")

        signals[name] = (asset, direction)
        # Max 1 trade per strategy per cycle
        if len(signals) >= 3:  # Max 3 strategies trade per cycle
            break

# Summary
log("---")
for name in STRATEGIES:
    strat_trades = [t for t in trades if t['strategy'] == name]
    if not strat_trades: continue
    w = sum(1 for t in strat_trades if t['win'])
    t = len(strat_trades)
    pnl = sum(t['profit'] for t in strat_trades)
    log(f"  {name:12s}: {w}/{t}={w/t*100:.0f}% pnl={pnl:+.1f}")
log("===")
