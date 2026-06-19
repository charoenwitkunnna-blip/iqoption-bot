#!/usr/bin/env python3
"""Quick diagnostic - check what all strategies see in the data"""
import sys, time, importlib
sys.path.insert(0, '/root/iqoption-bot/experiments')

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
api.change_balance(BALANCE_TYPE)
time.sleep(1)
print("Balance:", api.get_balance())

data = api.get_all_init_v2()
import iqoptionapi.constants as OP_code
all_assets = set()
for option in ["binary", "blitz"]:
    actives = data.get(option, {}).get("actives", {})
    for aid, active in actives.items():
        name = str(active.get("name", "")).split(".")[-1]
        if active.get("enabled") and not active.get("is_suspended"):
            if name not in OP_code.ACTIVES:
                OP_code.ACTIVES[name] = int(aid)
            all_assets.add(name)

payouts = api.get_all_profit()
top = sorted([(a, payouts.get(a, {}).get("turbo", 0)) for a in all_assets], key=lambda x: x[1], reverse=True)[:5]

import numpy as np
import talib

# Load strategies
strats = {}
for name, path in [("v2", "v2/strategy.py"), ("ml", "ml_strategy/strategy.py"), 
                    ("ensemble", "ensemble/strategy.py"), ("ms", "market_structure/strategy.py")]:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    strats[name] = mod

for a, p in top:
    candles = api.get_candles(a, 60, 120, time.time())
    if not candles or len(candles) < 50:
        continue
    closes = np.array([c["close"] for c in candles], dtype=float)
    highs = np.array([c["max"] for c in candles], dtype=float)
    lows = np.array([c["min"] for c in candles], dtype=float)
    
    rsi = talib.RSI(closes, timeperiod=14)
    adx = talib.ADX(highs, lows, closes, timeperiod=14)
    
    print(f"\n{a:25s} (payout={p}%)")
    print(f"  Price: {closes[-1]:.5f}  RSI(14): {rsi[-1]:.1f}  ADX(14): {adx[-1]:.1f}")
    
    for sname, smod in strats.items():
        if hasattr(smod, "analyze"):
            d, conf = smod.analyze(api, a, candles)
        else:
            d, conf = "N/A", 0
        print(f"  {sname:15s} -> {str(d):5s} ({conf:.1f}%)")

print("\nDone.")
