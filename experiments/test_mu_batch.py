"""Batch test mu_micro_momentum — run 5 trades back to back."""
import sys, time, json, importlib.util
sys.path.insert(0, '/root/iqoption-bot/experiments')
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

AMOUNT = 5
TRADES = 5
results_file = '/root/iqoption-bot/experiments/results/mu_micro_momentum_live_trades.json'

path = '/root/iqoption-bot/experiments/new_algos/mu_micro_momentum/strategy.py'
spec = importlib.util.spec_from_file_location('mu_micro_momentum', path)
mu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mu)

def scan_once(api):
    all_open = api.get_all_open_time()
    open_assets = list({k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}.keys())
    paying = {}
    for asset in open_assets[:40]:
        try:
            p = api.get_digital_payout(asset)
            if p and p >= 80:
                paying[asset] = p
        except:
            continue
    for asset in sorted(paying, key=paying.get, reverse=True):
        try:
            dir, conf = mu.analyze(api, asset)
            if conf >= 55:
                return (asset, dir, conf, paying[asset])
        except:
            continue
    return None

total_win = 0
total_loss = 0
total_pnl = 0.0

for i in range(TRADES):
    api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
    api.connect()
    api.change_balance('PRACTICE')
    time.sleep(2)

    signal = scan_once(api)
    if not signal:
        print(f"[{i+1}/{TRADES}] No signal")
        api._close_connect = lambda: None; api._close_connect()
        continue

    asset, direction, confidence, payout = signal
    ok, tid = api.buy(AMOUNT, asset, direction, 1)
    if not ok:
        print(f"[{i+1}/{TRADES}] BUY FAILED {asset} {tid}")
        api._close_connect(); continue

    print(f"[{i+1}/{TRADES}] {asset} {direction} conf={confidence}", end='', flush=True)
    time.sleep(68)

    result = api.check_win_digital_v2(tid)
    win = bool(result[0]) if isinstance(result, (list, tuple)) else bool(result)
    profit = AMOUNT * (payout / 100) if win else -AMOUNT

    total_win += 1 if win else 0
    total_loss += 0 if win else 1
    total_pnl += profit
    print(f" {'WIN ✅' if win else 'LOSS ❌'} profit={profit:+.1f} pnl={total_pnl:+.1f}")

    # Save
    trade = {"time": time.strftime('%Y-%m-%d %H:%M:%S'), "asset": asset,
             "direction": direction, "amount": AMOUNT, "confidence": confidence,
             "profit": profit, "win": win, "trade_id": tid}
    try:
        with open(results_file) as f:
            trades = json.load(f)
    except:
        trades = []
    trades.append(trade)
    with open(results_file, 'w') as f:
        json.dump(trades, f, indent=2)

    api._close_connect = lambda: None; api._close_connect()

print(f"\n{'='*40}")
print(f"RESULT: {total_win}W/{total_loss}L pnl={total_pnl:+.1f}")
print(f"WR: {total_win/(total_win+total_loss)*100:.0f}%" if (total_win+total_loss) > 0 else "No trades")
