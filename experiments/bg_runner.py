#!/usr/bin/env python3
"""
Generic background experiment runner.
Usage: python3 bg_runner.py <strategy_name> [--amount N] [--hours N]
Strategies: ml_strategy, market_structure, ensemble, v2
"""
import sys, os, time, json, importlib

STRATEGY = sys.argv[1] if len(sys.argv) > 1 else "ensemble"
AMOUNT = int(sys.argv[sys.argv.index("--amount") + 1]) if "--amount" in sys.argv else 5
RUN_HOURS = float(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 999

BASE_DIR = "/root/iqoption-bot/experiments"
LOG_FILE = f"{BASE_DIR}/results/{STRATEGY}_run.log"
RESULTS_FILE = f"{BASE_DIR}/results/{STRATEGY}_trades.json"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

log(f"=== {STRATEGY} BACKGROUND RUNNER started ===")

sys.path.insert(0, BASE_DIR)
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
if not check:
    log(f"Connection FAILED: {reason}")
    sys.exit(1)

api.change_balance(BALANCE_TYPE)
time.sleep(1)
balance = api.get_balance()
log(f"Connected. Balance: {balance} PRACTICE")

# Get assets
data = api.get_all_init_v2()
import iqoptionapi.constants as OP_code
all_assets = {}
for opt in ["binary", "blitz"]:
    for aid, act in data.get(opt, {}).get("actives", {}).items():
        name = str(act.get("name", "")).split(".")[-1]
        if act.get("enabled") and not act.get("is_suspended"):
            if name not in OP_code.ACTIVES:
                OP_code.ACTIVES[name] = int(aid)
            all_assets[name] = int(aid)

payouts = api.get_all_profit()
tradable = [(n, payouts.get(n, {}).get("turbo", payouts.get(n, {}).get("binary", 0)))
            for n in all_assets if payouts.get(n, {}).get("turbo", 0) >= 0.5]
tradable.sort(key=lambda x: x[1], reverse=True)
top_assets = [a for a, p in tradable[:15]]
log(f"Monitoring {len(top_assets)} assets")

# Load strategy
spec = importlib.util.spec_from_file_location(STRATEGY, f"{BASE_DIR}/{STRATEGY}/strategy.py")
strat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strat)
log(f"Loaded strategy: {getattr(strat, 'NAME', STRATEGY)}")

# Load history
trades = []
if os.path.exists(RESULTS_FILE):
    try:
        with open(RESULTS_FILE) as f:
            trades = json.load(f)
    except:
        trades = []

stats = {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0}
for t in trades:
    stats["total"] += 1
    if t.get("profit", 0) > 0:
        stats["wins"] += 1
    else:
        stats["losses"] += 1
    stats["pnl"] += t.get("profit", 0)

log(f"Loaded {stats['total']} previous trades. PnL: {stats['pnl']:.1f}")

start_time = time.time()
scan_count = 0

try:
    while True:
        if RUN_HOURS < 999 and (time.time() - start_time) > RUN_HOURS * 3600:
            log(f"Reached {RUN_HOURS}h limit, stopping")
            break
        
        scan_count += 1
        balance = api.get_balance()
        
        for asset in top_assets:
            try:
                candles = api.get_candles(asset, 60, 120, time.time())
                if not candles or len(candles) < 50:
                    continue
                
                direction = strat.analyze(api, asset, candles)
                if isinstance(direction, (tuple, list)):
                    direction, confidence = direction[0], direction[1] if len(direction) > 1 else 50
                else:
                    confidence = 50
                if direction and confidence >= 50:
                    amount = min(AMOUNT, max(3, int(balance * 0.03)))
                    tid, success = api.buy(amount, asset, direction, 1)
                    log(f"SIGNAL: {asset} {direction.upper()} x{amount} (conf={confidence:.0f}%) id={tid} ok={success}")
                    
                    if success:
                        time.sleep(65)
                        result = api.get_async_order(tid)
                        profit = result.get("profit", 0) - amount
                        win = profit > 0
                        
                        trade = {
                            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "asset": asset, "direction": direction,
                            "amount": amount, "confidence": confidence,
                            "profit": profit, "win": win
                        }
                        trades.append(trade)
                        stats["total"] += 1
                        if win:
                            stats["wins"] += 1
                        else:
                            stats["losses"] += 1
                        stats["pnl"] += profit
                        
                        wr = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
                        emoji = "WIN" if win else "LOSS"
                        log(f"  {emoji} profit={profit:.1f} ({stats['total']}t {wr:.0f}% wr pnl={stats['pnl']:.1f})")
                        
                        with open(RESULTS_FILE, "w") as f:
                            json.dump(trades, f, indent=2)
                        time.sleep(3)
            except Exception as e:
                import traceback
                log(f"  {asset} ERROR: {e} | {traceback.format_exc()[-200:].replace(chr(10), ' ')}")
                continue
        
        if scan_count % 6 == 0:
            elapsed = (time.time() - start_time) / 60
            wr = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
            log(f"[{scan_count}] {stats['total']}t {stats['wins']}w/{stats['losses']}l {wr:.0f}% pnl={stats['pnl']:.1f} bal={balance:.1f} ({elapsed:.0f}m)")
        
        time.sleep(15)
        
except KeyboardInterrupt:
    log("Interrupted")
finally:
    wr = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
    log(f"=== FINAL: {stats['total']}t {wr:.0f}% wr pnl={stats['pnl']:.1f} ===")
    with open(RESULTS_FILE, "w") as f:
        json.dump(trades, f, indent=2)
