"""Cron test: run all strategies and compare real results during active market."""
import sys, os, json, time
sys.path.insert(0, '/root/iqoption-bot/experiments')

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

STRATEGIES = ["rho_bounce", "sigma", "psi_conviction", "gamma_breakout", "zeta_hybrid", "iota_dead_market", "mu_micro_momentum"]
AMOUNT = 5
RESULTS_FILE = "/root/iqoption-bot/experiments/results/comparison_results.json"

def check_win(api, trade_id):
    try:
        result = api.check_win_digital_v2(trade_id)
        if isinstance(result, (list, tuple)):
            return bool(result[0])
        return bool(result)
    except:
        return False

results = {}
if os.path.exists(RESULTS_FILE):
    try:
        results = json.load(open(RESULTS_FILE))
    except:
        results = {}

for strat_name in STRATEGIES:
    print(f"\n--- {strat_name} ---")
    api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
    api.connect()
    api.change_balance("PRACTICE")
    time.sleep(2)

    # Load strategy
    import importlib.util
    path = os.path.join('/root/iqoption-bot/experiments/new_algos', strat_name, 'strategy.py')
    if not os.path.exists(path):
        print(f"  NOT FOUND")
        continue
    spec = importlib.util.spec_from_file_location(strat_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Scan assets (same as runner)
    all_open = api.get_all_open_time()
    open_assets = {k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}
    paying = {}
    for asset in list(open_assets.keys())[:50]:
        try:
            p = api.get_digital_payout(asset)
            if p and p >= 85:
                paying[asset] = p
        except:
            continue

    # Try to find and execute one trade
    trade_result = None
    for asset in sorted(paying, key=paying.get, reverse=True):
        try:
            candles = api.get_candles(asset, 60, 50, time.time())
            if not candles or len(candles) < 30:
                continue
        except:
            continue
        try:
            htf = None
            try:
                htf = api.get_candles(asset, 300, 10, time.time())
            except:
                pass
            direction, confidence = mod.analyze(api, asset, candles, htf)
        except:
            continue
        if direction is None:
            continue

        # Execute trade
        try:
            ok, tid = api.buy(AMOUNT, asset, direction, 1)
            if not ok:
                continue
        except:
            continue

        # Wait and check
        print(f"  {asset} {direction} conf={confidence}...", end="", flush=True)
        time.sleep(68)
        win = check_win(api, tid)
        profit = AMOUNT * (paying.get(asset, 87) / 100) if win else -AMOUNT
        print(f" {'WIN' if win else 'LOSS'} profit={profit:+.1f}")
        trade_result = {"asset": asset, "direction": direction,
                        "confidence": confidence, "win": win, "profit": profit,
                        "time": time.strftime('%H:%M:%S')}
        break

    if strat_name not in results:
        results[strat_name] = {"runs": [], "total_trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}

    if trade_result:
        results[strat_name]["runs"].append(trade_result)
        results[strat_name]["total_trades"] += 1
        if trade_result["win"]:
            results[strat_name]["wins"] += 1
        else:
            results[strat_name]["losses"] += 1
        results[strat_name]["pnl"] = round(results[strat_name]["pnl"] + trade_result["profit"], 2)

    api._close_connect = lambda: None
    api._close_connect()

# Print summary
print(f"\n{'='*60}")
print(f"COMPARISON RESULTS (as of {time.strftime('%Y-%m-%d %H:%M')})")
print(f"{'='*60}")
for s in sorted(results.keys()):
    r = results[s]
    t = r["total_trades"]
    if t == 0:
        print(f"  {s:20s}: 0 trades")
        continue
    wr = r["wins"] / t * 100
    print(f"  {s:20s}: {t}t {r['wins']}W/{r['losses']}L {wr:.0f}% pnl={r['pnl']:+.1f}")

json.dump(results, open(RESULTS_FILE, "w"), indent=2)
print(f"\nSaved to {RESULTS_FILE}")
