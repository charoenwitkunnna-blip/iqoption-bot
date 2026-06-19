"""Test iota on XAUUSD specifically — dead market confirmed."""
import sys, time, json, importlib.util
sys.path.insert(0, '/root/iqoption-bot/experiments')
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

AMOUNT = 5

path = '/root/iqoption-bot/experiments/new_algos/iota_dead_market/strategy.py'
spec = importlib.util.spec_from_file_location('iota_dead_market', path)
strat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strat)

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance('PRACTICE')
time.sleep(2)

# Specifically scan assets with low ADX (dead market candidates)
all_open = api.get_all_open_time()
open_assets = list({k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}.keys())

# Get payouts first
paying = {}
for asset in open_assets[:30]:
    try:
        p = api.get_digital_payout(asset)
        if p and p >= 80:
            paying[asset] = p
    except:
        continue

# Find dead assets and check signals
signals = []
for asset in sorted(paying, key=paying.get, reverse=True):
    try:
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 40:
            continue
        closes = [c['close'] for c in candles]
        highs = [c['max'] for c in candles]
        lows = [c['min'] for c in candles]
        adx_val = strat.adx(highs, lows, closes, 14)
        if adx_val is not None:
            print(f"{asset}: ADX={adx_val:.1f} payout={paying[asset]}%", end='')
            dir, conf = strat.analyze(api, asset, candles, None)
            if conf >= 60:
                print(f" -> SIGNAL {dir} conf={conf}")
                signals.append((asset, dir, conf, paying[asset], adx_val))
            else:
                print(f" -> no signal")
    except Exception as e:
        print(f"{asset}: error {e}")

print(f"\nFound {len(signals)} signals")
if not signals:
    api._close_connect = lambda: None
    api._close_connect()
    exit(0)

# Trade the best one (highest confidence)
signals.sort(key=lambda s: s[2], reverse=True)
asset, direction, confidence, payout, adx_val = signals[0]
print(f"\nTrading: {asset} {direction} conf={confidence} ADX={adx_val:.1f} payout={payout}%")

ok, tid = api.buy(AMOUNT, asset, direction, 1)
if not ok:
    print(f"BUY FAILED: {tid}")
    exit(1)

print(f"Bought! TID={tid}")
for s in range(68, 0, -10):
    print(f"\rWaiting {s}s...", end='')
    time.sleep(10)

result = api.check_win_digital_v2(tid)
if isinstance(result, (list, tuple)):
    win = bool(result[0])
else:
    win = bool(result)

profit = AMOUNT * (payout / 100) if win else -AMOUNT
print(f"\r{asset} {direction} {'WIN ✅' if win else 'LOSS ❌'} profit={profit:+.1f}")

api._close_connect = lambda: None
api._close_connect()
