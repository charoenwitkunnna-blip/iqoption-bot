#!/usr/bin/env python3
"""V2 strategy background runner - logs to file, scans every 15s, trades on signals"""
import sys, os, time, json, importlib
sys.path.insert(0, '/root/iqoption-bot/experiments')

LOG_FILE = "/root/iqoption-bot/experiments/results/v2_run.log"
RESULTS_FILE = "/root/iqoption-bot/experiments/results/v2_trades.json"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

log("=== V2 Strategy BACKGROUND RUNNER started ===")

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

# Get all open assets once
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
tradable = [(name, payouts.get(name, {}).get("turbo", payouts.get(name, {}).get("binary", 0))) 
            for name in all_assets if payouts.get(name, {}).get("turbo", 0) >= 0.5]
tradable.sort(key=lambda x: x[1], reverse=True)
top_assets = [a for a, p in tradable[:15]]
log(f"Monitoring {len(top_assets)} assets: {', '.join(top_assets[:5])}...")

# Load V2
spec = importlib.util.spec_from_file_location("v2", "/root/iqoption-bot/experiments/v2/strategy.py")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)

# Load existing trade history
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

log(f"Loaded {len(trades)} previous trades. PnL: {stats['pnl']:.1f}")

scan_count = 0
start_time = time.time()

try:
    while True:
        scan_count += 1
        balance = api.get_balance()
        
        for asset in top_assets:
            try:
                candles = api.get_candles(asset, 60, 120, time.time())
                if not candles or len(candles) < 50:
                    continue
                
                direction, confidence = v2.analyze(api, asset, candles)
                if direction and confidence >= 50:
                    amount = min(10, int(balance * 0.03))
                    if amount < 5:
                        amount = 5
                    
                    tid, success = api.buy(amount, asset, direction, 1)
                    log(f"SIGNAL: {asset} {direction.upper()} x{amount} (conf={confidence:.0f}%) id={tid} ok={success}")
                    
                    if success:
                        time.sleep(65)
                        result = api.get_async_order(tid)
                        profit = result.get("profit", 0) - amount
                        win = profit > 0
                        
                        trade = {
                            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "asset": asset,
                            "direction": direction,
                            "amount": amount,
                            "confidence": confidence,
                            "profit": profit,
                            "win": win
                        }
                        trades.append(trade)
                        stats["total"] += 1
                        if win:
                            stats["wins"] += 1
                        else:
                            stats["losses"] += 1
                            stats["pnl"] += profit
                        
                        wr = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
                        log(f"  {'WIN' if win else 'LOSS'} profit={profit:.1f} | ({stats['total']}t {wr:.0f}% wr pnl={stats['pnl']:.1f})")
                        
                        with open(RESULTS_FILE, "w") as f:
                            json.dump(trades, f, indent=2)
                        
                        time.sleep(3)
            except Exception as e:
                log(f"  {asset} ERROR: {e}")
                continue
        
        if scan_count % 10 == 0:
            elapsed = (time.time() - start_time) / 60
            wr = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
            log(f"[SCAN {scan_count}] {stats['total']}t {stats['wins']}w/{stats['losses']}l {wr:.0f}% pnl={stats['pnl']:.1f} balance={balance:.2f} elapsed={elapsed:.1f}m")
        
        time.sleep(15)
        
except KeyboardInterrupt:
    log("Interrupted")
finally:
    wr = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
    log(f"=== FINAL: {stats['total']}t {wr:.0f}% wr pnl={stats['pnl']:.1f} ===")
    with open(RESULTS_FILE, "w") as f:
        json.dump(trades, f, indent=2)
