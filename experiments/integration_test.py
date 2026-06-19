#!/usr/bin/env python3
"""Quick integration test for experiment runner"""
import sys, time, importlib
sys.path.insert(0, '/root/iqoption-bot/experiments')

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
api.change_balance(BALANCE_TYPE)
time.sleep(1)
print("Balance:", api.get_balance())

# Get top assets
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

payouts_dict = api.get_all_profit()
asset_payouts = []
for a in sorted(all_assets):
    ap = payouts_dict.get(a, {})
    payout = ap.get("turbo", ap.get("binary", 0))
    asset_payouts.append((a, payout))
asset_payouts.sort(key=lambda x: x[1], reverse=True)
top = [a for a, p in asset_payouts[:5]]
print("Top assets:", top)

# Load V2 strategy
spec = importlib.util.spec_from_file_location("v2", "/root/iqoption-bot/experiments/v2/strategy.py")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)

# Analyze
for a in top:
    candles = api.get_candles(a, 60, 120, time.time())
    if candles and len(candles) > 50:
        d, conf = v2.analyze(api, a, candles)
        print(f"  {a}: {d} ({conf:.1f}%)")

# Place one test trade on PRACTICE
for a in top:
    candles = api.get_candles(a, 60, 120, time.time())
    d, conf = v2.analyze(api, a, candles)
    if d and conf >= 50:
        trade_id, success = api.buy(5, a, d, 1)
        print(f"Trade: {a} {d} x5 -> id={trade_id} success={success}")
        if success:
            time.sleep(65)
            result = api.get_async_order(trade_id)
            profit = result.get("profit", 0) - 5
            print(f"  {'WIN' if profit > 0 else 'LOSS'} profit={profit:.1f}")
        break
else:
    print("No signals - runner will trade when market aligns")

print("DONE - Balance:", api.get_balance())
