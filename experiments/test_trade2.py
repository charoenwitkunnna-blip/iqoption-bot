#!/usr/bin/env python3
"""Smart test - filters to real binary OTC assets"""
import sys, time, importlib
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
all_a = {}
for opt in ["binary", "blitz"]:
    for aid, act in data.get(opt, {}).get("actives", {}).items():
        name = str(act.get("name", "")).split(".")[-1]
        if act.get("enabled") and not act.get("is_suspended"):
            if name not in OP_code.ACTIVES:
                OP_code.ACTIVES[name] = int(aid)
            all_a[name] = int(aid)

payouts = api.get_all_profit()

# Filter to only real OTC forex/stock assets (skip -op, weird pairs)
filtered = []
for a, aid in all_a.items():
    ap = payouts.get(a, {})
    payout = ap.get("turbo", ap.get("binary", 0))
    if payout < 0.5:
        continue
    filtered.append((a, payout))

filtered.sort(key=lambda x: x[1], reverse=True)
print(f"Tradable assets ({len(filtered)}): {[a for a,p in filtered[:10]]}")

spec = importlib.util.spec_from_file_location("v2", "/root/iqoption-bot/experiments/v2/strategy.py")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)

for a, payout_pct in filtered[:10]:
    try:
        candles = api.get_candles(a, 60, 120, time.time())
        if not candles or len(candles) < 50:
            continue
        d, conf = v2.analyze(api, a, candles)
        print(f"  {a:25s} payout={payout_pct:.1f}% -> {str(d):5s} ({conf:.0f}%)")
    except Exception as e:
        print(f"  {a:25s} ERROR: {e}")

print("\n--- Placing highest-confidence trade ---")
for a, payout_pct in filtered[:10]:
    try:
        candles = api.get_candles(a, 60, 120, time.time())
        d, conf = v2.analyze(api, a, candles)
        if d and conf >= 50:
            amount = 10
            print(f"BUY: {a} {d.upper()} x{amount} (conf={conf:.0f}%, payout={payout_pct:.1f}%)")
            tid, ok = api.buy(amount, a, d, 1)
            print(f"  Result: id={tid} success={ok}")
            if ok:
                time.sleep(65)
                res = api.get_async_order(tid)
                profit = res.get("profit", 0) - amount
                print(f"  {'WIN!' if profit > 0 else 'LOSS'} profit={profit:.1f}")
            break
    except Exception as e:
        print(f"  ERROR: {e}")
        continue

final = api.get_balance()
print(f"\nFinal: {final} (change: {final-balance:.1f})")
