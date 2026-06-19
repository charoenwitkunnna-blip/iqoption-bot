#!/usr/bin/env python3
"""Experiment: Volatility Breakout — trade when candle range exceeds 2x avg range.
Higher volatility = stronger directional moves = better accuracy."""
import sys, os, time, json
import pandas as pd
import numpy as np

AMOUNT = 8
BASE_DIR = "/root/iqoption-bot/experiments"

sys.path.insert(0, BASE_DIR)
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

results_file = f"{BASE_DIR}/results/volatility_trades.json"
log_file = f"{BASE_DIR}/results/volatility_stable.log"

def log(msg):
    with open(log_file, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
if not check:
    log("FAIL")
    sys.exit(1)
api.change_balance(BALANCE_TYPE)
time.sleep(1)
balance = api.get_balance()

# Assets
data = api.get_all_init_v2()
import iqoptionapi.constants as OP_code
for opt in ["binary", "blitz"]:
    for aid, act in data.get(opt, {}).get("actives", {}).items():
        name = str(act.get("name", "")).split(".")[-1]
        if act.get("enabled") and not act.get("is_suspended"):
            if name not in OP_code.ACTIVES:
                OP_code.ACTIVES[name] = int(aid)
payouts = api.get_all_profit()
all_assets = {}
for opt in ["binary", "blitz"]:
    for aid, act in data.get(opt, {}).get("actives", {}).items():
        name = str(act.get("name", "")).split(".")[-1]
        if act.get("enabled") and not act.get("is_suspended"):
            all_assets[name] = int(aid)
top_assets = sorted([(n, payouts.get(n, {}).get("turbo", payouts.get(n, {}).get("binary", 0)))
     for n in all_assets], key=lambda x: x[1], reverse=True)[:5]
assets = [a for a, p in top_assets]

trades = []
if os.path.exists(results_file):
    with open(results_file) as f:
        trades = json.load(f)
stats = {"total": len(trades), "wins": sum(1 for t in trades if t.get("profit",0)>0),
         "pnl": sum(t.get("profit",0) for t in trades)}

log(f"VOL-TEST: bal={balance:.1f}")
for asset in assets:
    try:
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 30:
            continue
        
        df = pd.DataFrame(candles)
        ranges = df['max'] - df['min']
        avg_range = ranges.iloc[:-2].mean()
        last_range = ranges.iloc[-2]
        prev_close = df['close'].iloc[-2]
        prev_open = df['open'].iloc[-2]
        body = prev_close - prev_open
        
        # Volatility breakout: current range > 1.5x avg range
        if last_range < avg_range * 1.5:
            continue
        
        # Direction: body > 0 = bull candle -> CALL, bear -> PUT
        if body > 0:
            direction = "call"
        else:
            direction = "put"
        
        amount = min(AMOUNT, max(3, int(balance * 0.03)))
        ok, tid = api.buy(amount, asset, direction, 1)
        log(f"SIG:{asset} {direction.upper()} {amount}(V={last_range/avg_range:.1f}x) ok={ok}")
        if ok:
            time.sleep(67)
            order = api.get_async_order(tid)
            if order:
                profit = order.get("option-closed",{}).get("msg",{}).get("profit_amount",0) - amount
            else:
                profit = -amount
            win = profit > 0
            trades.append({"time":time.strftime("%Y-%m-%d %H:%M:%S"),"asset":asset,
                          "direction":direction,"amount":amount,"profit":profit,"win":win})
            stats["total"]+=1; stats["pnl"]+=profit
            if win: stats["wins"]+=1
            wr = stats["wins"]/stats["total"]*100 if stats["total"] else 0
            log(f"  {'WIN' if win else 'LOSS'} p={profit:.1f} ({stats['total']}t {wr:.0f}% pnl={stats['pnl']:.1f})")
            json.dump(trades, open(results_file,"w"), indent=2)
    except Exception as e:
        log(f"  {asset} err: {e}")

wr = stats["wins"]/stats["total"]*100 if stats["total"] else 0
log(f"CYCLE: {stats['total']}t {stats['wins']}w/{stats['total']-stats['wins']}l {wr:.0f}% pnl={stats['pnl']:.1f}")
