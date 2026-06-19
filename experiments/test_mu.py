"""Quick test mu_micro_momentum — one trade on PRACTICE."""
import sys, time, json, importlib.util
sys.path.insert(0, '/root/iqoption-bot/experiments')
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

AMOUNT = 5

path = '/root/iqoption-bot/experiments/new_algos/mu_micro_momentum/strategy.py'
spec = importlib.util.spec_from_file_location('mu_micro_momentum', path)
mu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mu)
print(f"Loaded {mu.NAME}")

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance('PRACTICE')
time.sleep(2)

# Quick scan for signals
all_open = api.get_all_open_time()
open_assets = list({k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}.keys())

paying = {}
for asset in open_assets[:30]:
    try:
        p = api.get_digital_payout(asset)
        if p and p >= 80:
            paying[asset] = p
    except:
        continue

print(f"Scanning {len(paying)} paying assets for micro-momentum...")
signals = []
for asset in sorted(paying, key=paying.get, reverse=True):
    try:
        dir, conf = mu.analyze(api, asset)
        if conf >= 55:
            signals.append((asset, dir, conf, paying[asset]))
            print(f"  {asset} {dir} conf={conf}")
    except Exception as e:
        print(f"  {asset}: error {e}")

print(f"\nFound {len(signals)} signal(s)")
if not signals:
    print("No trades")
    # Still show 5-sec candle example for fun
    c5 = api.get_candles(signals if len(signals) > 0 else list(paying.keys())[0], 5, 50, time.time()) if len(signals) > 0 else []
    if not c5 and paying:
        asset = list(paying.keys())[0]
        c5 = api.get_candles(asset, 5, 50, time.time())
        closes = [c['close'] for c in c5]
        print(f"\n5-sec sample from {asset}: last 5 closes = {[round(c,4) for c in closes[-5:]]}")
    api._close_connect = lambda: None; api._close_connect()
    exit(0)

# Trade best signal
asset, direction, confidence, payout = signals[0]
print(f"\nTrading: {asset} {direction} conf={confidence}")

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

api._close_connect = lambda: None; api._close_connect()
