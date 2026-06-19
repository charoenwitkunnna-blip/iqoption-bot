"""Quick test iota_dead_market — find one signal, trade it, report result."""
import sys, time, json, importlib.util
sys.path.insert(0, '/root/iqoption-bot/experiments')
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

AMOUNT = 5
results_file = '/root/iqoption-bot/experiments/results/iota_dead_market_live_trades.json'

# Load strategy
path = '/root/iqoption-bot/experiments/new_algos/iota_dead_market/strategy.py'
spec = importlib.util.spec_from_file_location('iota_dead_market', path)
strat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strat)
print(f"Loaded {strat.NAME}")

# Connect
api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance('PRACTICE')
time.sleep(2)

# Quick scan — only check first 20 open assets
all_open = api.get_all_open_time()
open_assets = list({k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}.keys())

paying = {}
for asset in open_assets[:20]:
    try:
        p = api.get_digital_payout(asset)
        if p and p >= 80:
            paying[asset] = p
    except:
        continue

print(f"Scanning {len(paying)} paying assets...")

found = None
for asset in sorted(paying, key=paying.get, reverse=True):
    try:
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 50:
            continue
    except:
        continue
    try:
        direction, confidence = strat.analyze(api, asset, candles, None)
    except Exception as e:
        print(f"  {asset}: analyze error {e}")
        continue
    if direction and confidence >= 60:
        found = (asset, direction, confidence, paying.get(asset, 87))
        print(f"  SIGNAL: {asset} {direction} conf={confidence} payout={paying.get(asset, 87)}%")
        break

if not found:
    print("No signals in first 20 assets")
    api._close_connect = lambda: None
    api._close_connect()
    exit(0)

asset, direction, confidence, payout = found

# Execute
ok, tid = api.buy(AMOUNT, asset, direction, 1)
if not ok:
    print(f"BUY FAILED: {tid}")
    api._close_connect()
    exit(1)

print(f"Bought {asset} {direction} TID={tid}")

# Wait
for s in range(68, 0, -10):
    print(f"\rWaiting {s}s...", end='')
    time.sleep(10)
print(f"\rChecking result...")

# Check win
result = api.check_win_digital_v2(tid)
if isinstance(result, (list, tuple)):
    win = bool(result[0])
else:
    win = bool(result)

profit = AMOUNT * (payout / 100) if win else -AMOUNT
status = "WIN ✅" if win else "LOSS ❌"
print(f"\n{asset} {direction} {status} profit={profit:+.1f}")

# Save
trade = {
    "time": time.strftime('%Y-%m-%d %H:%M:%S'),
    "asset": asset, "direction": direction,
    "amount": AMOUNT, "confidence": confidence,
    "profit": profit, "win": win, "trade_id": tid
}
trades = []
try:
    with open(results_file) as f:
        trades = json.load(f)
except:
    pass
trades.append(trade)
with open(results_file, 'w') as f:
    json.dump(trades, f, indent=2)

w = sum(1 for t in trades if t['win'])
t = len(trades)
print(f"Total: {t}t {w}w/{t-w}l pnl={sum(t['profit'] for t in trades):+.1f}")

api._close_connect = lambda: None
api._close_connect()
