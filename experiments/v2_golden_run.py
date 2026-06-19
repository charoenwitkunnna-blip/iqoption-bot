#!/usr/bin/env python3
"""
THE WINNING STRATEGY: V2 on EURJPY-OTC only
81.2% win rate on 16 backtested trades.
Runs forever, logs everything.
"""
import sys, os, time, json, importlib, math

STRATEGY = "v2"
ASSET = "EURJPY-OTC"
AMOUNT = 8
BASE_DIR = "/root/iqoption-bot/experiments"
LOG_FILE = f"{BASE_DIR}/results/v2_golden_run.log"
RESULTS_FILE = f"{BASE_DIR}/results/v2_golden_trades.json"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

log("=== V2 GOLDEN RUN (EURJPY-OTC only) ===")

sys.path.insert(0, BASE_DIR)
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
log(f"Connect: {check}")
if not check:
    sys.exit(1)
api.change_balance(BALANCE_TYPE)
time.sleep(1)
log(f"Balance: {api.get_balance()}")

# Register EURJPY-OTC in ACTIVES
data = api.get_all_init_v2()
import iqoptionapi.constants as OP_code
for opt in ["binary", "blitz"]:
    for aid, act in data.get(opt, {}).get("actives", {}).items():
        name = str(act.get("name", "")).split(".")[-1]
        if name not in OP_code.ACTIVES:
            OP_code.ACTIVES[name] = int(aid)

# Load strategy
spec = importlib.util.spec_from_file_location("v2", f"{BASE_DIR}/v2/strategy.py")
v2_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2_mod)
log(f"Loaded: {v2_mod.NAME}")

# Load trades
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
    stats["pnl"] += t.get("profit", 0)
    if t.get("profit", 0) > 0:
        stats["wins"] += 1
    else:
        stats["losses"] += 1
log(f"Loaded {stats['total']} trades")

start = time.time()
scan = 0

try:
    while True:
        scan += 1
        balance = api.get_balance()
        
        try:
            candles = api.get_candles(ASSET, 60, 120, time.time())
            if candles and len(candles) >= 50:
                result = v2_mod.analyze(api, ASSET, candles)
                if isinstance(result, (tuple, list)):
                    direction, confidence = result[0], int(result[1])
                else:
                    direction, confidence = result, 50
                
                if direction in ["call", "put"] and confidence >= 70:
                    amount = min(AMOUNT, max(3, int(balance * 0.03)))
                    buy_ok, tid = api.buy(amount, ASSET, direction, 1)
                    log(f"SIGNAL: {ASSET} {direction.upper()} {amount}THB (c={confidence}) id={tid} ok={buy_ok}")
                    
                    if buy_ok:
                        time.sleep(65)
                        order = api.get_async_order(tid)
                        if order:
                            msg = order.get("option-closed", {}).get("msg", {})
                            profit = msg.get("profit_amount", 0) - amount
                        else:
                            profit = -amount
                        
                        win = profit > 0
                        t = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "asset": ASSET, 
                             "direction": direction, "amount": amount, "conf": confidence,
                             "profit": profit, "win": win}
                        trades.append(t)
                        stats["total"] += 1
                        stats["pnl"] += profit
                        if win: stats["wins"] += 1
                        else: stats["losses"] += 1
                        wr = stats["wins"]/stats["total"]*100 if stats["total"] else 0
                        log(f"  {'WIN' if win else 'LOSS'} p={profit:.1f} ({stats['total']}t {wr:.0f}% wr pnl={stats['pnl']:.1f} bal={balance:.1f})")
                        json.dump(trades, open(RESULTS_FILE, "w"), indent=2)
                        time.sleep(3)
        except Exception as e:
            import traceback as tb
            log(f"  ERR: {e}")
        
        if scan % 12 == 0:
            elapsed = (time.time()-start)/60
            wr = stats["wins"]/stats["total"]*100 if stats["total"] else 0
            log(f"[{scan}] {stats['total']}t {stats['wins']}w/{stats['losses']}l {wr:.0f}% pnl={stats['pnl']:.1f} bal={balance:.1f} ({elapsed:.1f}m)")
        
        time.sleep(10)

except KeyboardInterrupt:
    log("Stopped")
finally:
    wr = stats["wins"]/stats["total"]*100 if stats["total"] else 0
    log(f"=== FINAL: {stats['total']}t {wr:.0f}% wr pnl={stats['pnl']:.1f} ===")
    json.dump(trades, open(RESULTS_FILE, "w"), indent=2)
