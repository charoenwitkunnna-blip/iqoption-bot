#!/usr/bin/env python3
"""Diagnose why all strategies are losing - compare indicator predictions vs actual movement"""
import sys, time, importlib, numpy as np, talib
sys.path.insert(0, '/root/iqoption-bot/experiments')

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
api.change_balance(BALANCE_TYPE)
time.sleep(1)

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

print(f"{'Asset':25s} {'Price':>10s} {'RSI':>5s} {'ADX':>5s} {'Signal':>7s} {'Conf':>5s} {'Next':>8s} {'Hit?':>5s}")
print("-" * 75)

for a, payout_pct in tradable[:10]:
    candles = api.get_candles(a, 60, 120, time.time())
    if not candles or len(candles) < 50:
        continue
    closes = np.array([c["close"] for c in candles], dtype=float)
    highs = np.array([c["max"] for c in candles], dtype=float)
    lows = np.array([c["min"] for c in candles], dtype=float)
    
    rsi = talib.RSI(closes, timeperiod=14)[-1]
    adx = talib.ADX(highs, lows, closes, timeperiod=14)[-1]
    macd, macd_signal, _ = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)
    
    # Strategy prediction using ML
    spec = importlib.util.spec_from_file_location("ml", "/root/iqoption-bot/experiments/ml_strategy/strategy.py")
    ml = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ml)
    d, conf = ml.analyze(api, a, candles)
    
    # Check what actually happened in the next candle
    next_candles = api.get_candles(a, 60, 5, time.time())
    if len(next_candles) >= 2:
        actual_move = next_candles[-1]["close"] - next_candles[-2]["close"]
        was_call = actual_move > 0
        hit = (d == "call" and was_call) or (d == "put" and not was_call) or d is None
    else:
        actual_move = 0
        hit = "?"
    
    hit_str = "Y" if hit else ("N" if d else "-")
    signal = str(d or "·")[:5]
    
    print(f"{a:25s} {closes[-1]:>10.5f} {rsi:>5.0f} {adx:>5.0f} {signal:>7s} {conf:>4.0f}% {actual_move:>+8.5f} {hit_str:>5s}")

print()
print("Analysis complete. Hit rate tells us if strategies are directionally correct.")
