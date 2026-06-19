#!/usr/bin/env python3
"""Run V2 strategy on PRACTICE - places a trade if signal exists"""
import sys, time, importlib, json
sys.path.insert(0, '/root/iqoption-bot/experiments')

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
api.change_balance(BALANCE_TYPE)
time.sleep(1)
balance = api.get_balance()
print(f"Balance: {balance} PRACTICE")

# Get assets
data = api.get_all_init_v2()
import iqoptionapi.constants as OP_code
all_a = set()
for opt in ["binary", "blitz"]:
    for aid, act in data.get(opt, {}).get("actives", {}).items():
        name = str(act.get("name", "")).split(".")[-1]
        if act.get("enabled") and not act.get("is_suspended"):
            if name not in OP_code.ACTIVES:
                OP_code.ACTIVES[name] = int(aid)
            all_a.add(name)

payouts = api.get_all_profit()
top = sorted([(a, payouts.get(a, {}).get("turbo", 0)) for a in all_a], key=lambda x: x[1], reverse=True)

spec = importlib.util.spec_from_file_location("v2", "/root/iqoption-bot/experiments/v2/strategy.py")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)

# First pass - find the best signal
best = None
for a, payout_pct in top[:10]:
    try:
        candles = api.get_candles(a, 60, 120, time.time())
        d, conf = v2.analyze(api, a, candles)
        if d and conf >= 50:
            print(f"SIGNAL: {a} {d} conf={conf:.0f}% payout={payout_pct}%")
            if best is None or conf > best[2]:
                best = (a, d, conf, payout_pct)
    except:
        pass

if best:
    a, d, conf, payout_pct = best
    print(f"\nPlacing trade: {a} {d.upper()} x{15} (conf={conf:.0f}%)")
    trade_id, success = api.buy(15, a, d, 1)
    print(f"Trade result: id={trade_id} success={success}")
    if success:
        for i in range(65):
            time.sleep(1)
            if i % 15 == 0:
                print(f"  Waiting... {i+1}s")
        result = api.get_async_order(trade_id)
        profit = result.get("profit", 0) - 15
        print(f"\nRESULT: {'WIN' if profit > 0 else 'LOSS'} profit={profit:.1f}")
    else:
        print("Trade failed")
else:
    print("No signals found - rerun when market moves")
    # Place anyway with first signal we see
    for a, payout_pct in top[:10]:
        candles = api.get_candles(a, 60, 120, time.time())
        d, conf = v2.analyze(api, a, candles)
        if d:
            print(f"\nPlacing trade: {a} {d.upper()} x{5} (conf={conf:.0f}%)")
            trade_id, success = api.buy(5, a, d, 1)
            print(f"Trade: id={trade_id} success={success}")
            if success:
                time.sleep(65)
                result = api.get_async_order(trade_id)
                profit = result.get("profit", 0) - 5
                print(f"RESULT: {'WIN' if profit > 0 else 'LOSS'} profit={profit:.1f}")
            break

final = api.get_balance()
print(f"Final balance: {final} (change: {final-balance:.1f})")
print("DONE")
