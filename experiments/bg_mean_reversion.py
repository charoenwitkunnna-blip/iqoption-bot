#!/usr/bin/env python3
"""Mean Reversion Strategy - PRACTICE runner"""
import sys, os, time, json, importlib
sys.path.insert(0, '/root/iqoption-bot/experiments')

STRATEGY = "mean_reversion"
BASE = '/root/iqoption-bot/experiments/results'
LOG = os.path.join(BASE, f'{STRATEGY}_run.log')
TF = os.path.join(BASE, f'{STRATEGY}_trades.json')

def log(m):
    with open(LOG, 'a') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {m}\n")
    print(m)

log("=== MEAN REVERSION RUNNER START ===")

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
if not check:
    log(f"FAILED: {reason}")
    sys.exit(1)
api.change_balance(BALANCE_TYPE)
time.sleep(1)
log(f"Connected: {api.get_balance()} PRACTICE")

# Get assets
data = api.get_all_init_v2()
import iqoptionapi.constants as OP_code
all_a = {}
for opt in ['binary', 'blitz']:
    for aid, act in data.get(opt, {}).get('actives', {}).items():
        name = str(act.get('name', '')).split('.')[-1]
        if act.get('enabled') and not act.get('is_suspended'):
            if name not in OP_code.ACTIVES:
                OP_code.ACTIVES[name] = int(aid)
            all_a[name] = int(aid)
payouts = api.get_all_profit()
tradable = [(n, payouts.get(n, {}).get('turbo', 0)) for n in all_a if payouts.get(n, {}).get('turbo', 0) >= 0.5]
tradable.sort(key=lambda x: x[1], reverse=True)
top = [a for a, p in tradable[:15]]
log(f"Monitoring {len(top)} assets")

# Load strategy
spec = importlib.util.spec_from_file_location(STRATEGY, f'{BASE}/../{STRATEGY}/strategy.py')
strat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strat)
log(f"Loaded: {strat.NAME}")

# Load history
trades = []
if os.path.exists(TF):
    try:
        with open(TF) as f:
            trades = json.load(f)
    except:
        trades = []

stats = {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0, "consecutive_losses": 0}
for t in trades:
    stats["total"] += 1
    if t.get("profit", 0) > 0:
        stats["wins"] += 1
    else:
        stats["losses"] += 1
        stats["consecutive_losses"] += 1
    if t.get("profit", 0) > 0:
        stats["consecutive_losses"] = 0
    stats["pnl"] += t.get("profit", 0)

log(f"History: {stats['total']}t {stats['wins']}w/{stats['losses']}l pnl={stats['pnl']:.1f}")

start = time.time()
scans = 0

try:
    while time.time() - start < 7200:  # 2 hours max
        scans += 1
        bal = api.get_balance()
        
        for asset in top:
            try:
                candles = api.get_candles(asset, 60, 120, time.time())
                if not candles or len(candles) < 50:
                    continue
                
                direction, confidence = strat.analyze(api, asset, candles)
                if direction and confidence >= 40:
                    # Circuit breaker: stop after 3 consecutive losses
                    if stats["consecutive_losses"] >= 3:
                        log(f"CIRCUIT BREAKER: {stats['consecutive_losses']} consecutive losses, skipping {asset}")
                        continue
                    
                    amt = max(3, min(5, int(bal * 0.02)))
                    tid, ok = api.buy(amt, asset, direction, 1)
                    log(f"SIGNAL: {asset} {direction.upper()} x{amt} (conf={confidence:.0f}%) id={tid} ok={ok}")
                    
                    if ok:
                        time.sleep(65)
                        r = api.get_async_order(tid)
                        profit = r.get('profit', 0) - amt
                        win = profit > 0
                        stats["total"] += 1
                        if win:
                            stats["wins"] += 1
                            stats["consecutive_losses"] = 0
                        else:
                            stats["losses"] += 1
                            stats["consecutive_losses"] += 1
                        stats["pnl"] += profit
                        
                        trades.append({
                            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "asset": asset, "direction": direction,
                            "amount": amt, "confidence": confidence,
                            "profit": profit, "win": win
                        })
                        
                        wr = stats["wins"] / stats["total"] * 100 if stats["total"] > 0 else 0
                        log(f"  {'WIN' if win else 'LOSS'} p={profit:.1f} ({stats['total']}t {wr:.0f}% pnl={stats['pnl']:.1f} consec_loss={stats['consecutive_losses']})")
                        
                        with open(TF, "w") as f:
                            json.dump(trades, f, indent=2)
                        time.sleep(3)
            except Exception as e:
                log(f"  {asset} ERR: {e}")
                continue
        
        if scans % 6 == 0:
            elapsed = (time.time() - start) / 60
            wr = stats["wins"] / stats["total"] * 100 if stats["total"] > 0 else 0
            log(f"[{scans}] {stats['total']}t {stats['wins']}w/{stats['losses']}l {wr:.0f}% pnl={stats['pnl']:.1f} bal={bal:.1f} ({elapsed:.0f}m)")
        
        time.sleep(15)
except KeyboardInterrupt:
    log("Interrupted")

wr = stats["wins"] / stats["total"] * 100 if stats["total"] > 0 else 0
log(f"=== FINAL: {stats['total']}t {wr:.0f}% wr pnl={stats['pnl']:.1f} ===")
with open(TF, "w") as f:
    json.dump(trades, f, indent=2)
