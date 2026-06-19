#!/usr/bin/env python3
"""Standalone replica_exact runner"""
import sys, os, time, json, importlib

STRATEGY_NAME = "replica_exact"
AMOUNT = 10
BASE_DIR = "/root/iqoption-bot/experiments"
LOG_FILE = f"{BASE_DIR}/results/{STRATEGY_NAME}_standalone.log"
RESULTS_FILE = f"{BASE_DIR}/results/{STRATEGY_NAME}_trades.json"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

log(f"=== {STRATEGY_NAME} STANDALONE ===")

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
balance = api.get_balance()
log(f"Balance: {balance}")

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
top_assets = sorted(
    [(n, payouts.get(n, {}).get("turbo", payouts.get(n, {}).get("binary", 0)))
     for n in all_assets],
    key=lambda x: x[1], reverse=True
)[:15]
top_assets = [a for a, p in top_assets]
log(f"Assets: {len(top_assets)}")

# Load strategy
spec = importlib.util.spec_from_file_location(
    STRATEGY_NAME, f"{BASE_DIR}/{STRATEGY_NAME}/strategy.py"
)
strat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strat)
log(f"Loaded: {strat.NAME}")

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
log(f"Loaded {stats['total']} trades")

start_time = time.time()
scan_count = 0

try:
    while True:
        scan_count += 1
        balance = api.get_balance()

        for asset in top_assets:
            try:
                candles = api.get_candles(asset, 60, 120, time.time())
                if not candles or len(candles) < 50:
                    continue

                result = strat.analyze(api, asset, candles)
                # result is either None, "call"/"put" string, or (direction, confidence) tuple
                if isinstance(result, (tuple, list)):
                    direction, confidence = result[0], int(result[1]) if len(result) > 1 else 50
                else:
                    direction, confidence = result, 50

                if direction and confidence >= 50:
                    amount = min(AMOUNT, max(3, int(balance * 0.03)))
                    buy_ok, tid = api.buy(amount, asset, direction, 1)
                    log(f"SIGNAL: {asset} {direction.upper()} x{amount} (c={confidence}) id={tid} ok={buy_ok}")

                    if buy_ok:
                        time.sleep(65)
                        order = api.get_async_order(tid)
                        if order:
                            msg = order.get("option-closed", {}).get("msg", {})
                            profit = msg.get("profit_amount", 0) - amount
                        else:
                            profit = -amount

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
                        log(f"  {'WIN' if win else 'LOSS'} profit={profit:.1f} ({stats['total']}t {wr:.0f}% wr pnl={stats['pnl']:.1f})")

                        with open(RESULTS_FILE, "w") as f:
                            json.dump(trades, f, indent=2)
                        time.sleep(3)
            except Exception as e:
                import traceback as tb
                log(f"  {asset} ERR: {e} | {''.join(tb.format_exception_only(type(e), e)).strip()}")
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
