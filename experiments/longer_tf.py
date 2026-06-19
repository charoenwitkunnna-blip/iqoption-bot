#!/usr/bin/env python3
"""Experiment: 3-minute expiry with replica_exact signals."""
import sys, os, time, json, importlib
import pandas as pd
import pandas_ta as ta
import numpy as np

AMOUNT = 8
EXPIRE_MINS = 3
TIMEFRAME = 60
BASE_DIR = "/root/iqoption-bot/experiments"

sys.path.insert(0, BASE_DIR)
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

results_file = f"{BASE_DIR}/results/longer_tf_trades.json"
log_file = f"{BASE_DIR}/results/longer_tf_stable.log"

def log(msg):
    with open(log_file, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def analyze(api, asset, candles):
    """Replica of the winning strategy with HTF filter"""
    try:
        htf = api.get_candles(asset, 300, 60, time.time())
        if not htf or len(htf) < 55:
            return None
        df_htf = pd.DataFrame(htf)
        htf_close = df_htf['close']
        htf_ema = ta.ema(htf_close, length=50)
        if htf_ema is None or htf_ema.empty or htf_ema.isna().iloc[-1]:
            return None
        htf_bull = htf_close.iloc[-1] > htf_ema.iloc[-1]
        htf_bear = htf_close.iloc[-1] < htf_ema.iloc[-1]

        df = pd.DataFrame(candles)
        close = df['close']
        fast_rsi = ta.rsi(close, length=5)
        slow_rsi = ta.rsi(close, length=14)
        if fast_rsi is None or slow_rsi is None or fast_rsi.empty or slow_rsi.empty:
            return None
        
        fast_p = fast_rsi.shift(1)
        slow_p = slow_rsi.shift(1)
        cross_up = ((fast_p <= slow_p) & (fast_rsi > slow_rsi)).fillna(False)
        cross_dn = ((fast_p >= slow_p) & (fast_rsi < slow_rsi)).fillna(False)
        
        if cross_up.iloc[-1] and slow_rsi.iloc[-1] < 40 and htf_bull:
            return "call"
        elif cross_dn.iloc[-1] and slow_rsi.iloc[-1] > 60 and htf_bear:
            return "put"
        elif cross_up.iloc[-1] and slow_rsi.iloc[-1] > 50 and htf_bull:
            return "call"
        elif cross_dn.iloc[-1] and slow_rsi.iloc[-1] < 50 and htf_bear:
            return "put"
    except:
        pass
    return None

# Connect
api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
if not check:
    log("FAIL")
    sys.exit(1)
api.change_balance(BALANCE_TYPE)
time.sleep(1)
balance = api.get_balance()

# Get assets
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

top_assets = sorted(
    [(n, payouts.get(n, {}).get("turbo", payouts.get(n, {}).get("binary", 0)))
     for n in all_assets],
    key=lambda x: x[1], reverse=True
)[:5]
assets = [a for a, p in top_assets]

# Load previous trades
trades = []
if os.path.exists(results_file):
    with open(results_file) as f:
        trades = json.load(f)
stats = {"total": len(trades), "wins": sum(1 for t in trades if t.get("profit",0)>0),
         "pnl": sum(t.get("profit",0) for t in trades)}

log(f"3MIN-TEST: bal={balance:.1f}")
for asset in assets:
    try:
        candles = api.get_candles(asset, TIMEFRAME, 120, time.time())
        if not candles or len(candles) < 50:
            continue
        result = analyze(api, asset, candles)
        if result in ["call", "put"]:
            amount = min(AMOUNT, max(3, int(balance * 0.03)))
            ok, tid = api.buy(amount, asset, result, EXPIRE_MINS)
            log(f"SIG:{asset} {result.upper()} {amount}/3min ok={ok}")
            if ok:
                time.sleep(EXPIRE_MINS * 60 + 10)
                order = api.get_async_order(tid)
                if order:
                    profit = order.get("option-closed",{}).get("msg",{}).get("profit_amount",0) - amount
                else:
                    profit = -amount
                win = profit > 0
                trades.append({"time":time.strftime("%Y-%m-%d %H:%M:%S"),"asset":asset,
                              "direction":result,"amount":amount,"profit":profit,"win":win})
                stats["total"]+=1; stats["pnl"]+=profit
                if win: stats["wins"]+=1
                wr = stats["wins"]/stats["total"]*100 if stats["total"] else 0
                log(f"  {'WIN' if win else 'LOSS'} p={profit:.1f} ({stats['total']}t {wr:.0f}% pnl={stats['pnl']:.1f})")
                json.dump(trades, open(results_file,"w"), indent=2)
    except Exception as e:
        log(f"  {asset} err: {e}")

wr = stats["wins"]/stats["total"]*100 if stats["total"] else 0
log(f"CYCLE: {stats['total']}t {stats['wins']}w/{stats['total']-stats['wins']}l {wr:.0f}% pnl={stats['pnl']:.1f}")
