#!/usr/bin/env python3
"""REAL balance — replica_exact strategy via stable cycle."""
import sys, os, time, json, importlib

STRAT_NAME = "replica_exact"
AMOUNT = 31  # Distinct from gamma's 30
BASE_DIR = "/root/iqoption-bot"
RESULTS_DIR = os.path.join(BASE_DIR, "experiments", "results")
LOG_FILE = os.path.join(RESULTS_DIR, "replica_real.log")
TRADES_FILE = os.path.join(RESULTS_DIR, "replica_real_trades.json")

sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "experiments"))

# Use REAL config
import config as cfg
from iqoptionapi.stable_api import IQ_Option

strat = importlib.import_module(f"replica_exact.strategy")

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

trades = []
if os.path.exists(TRADES_FILE):
    try:
        trades = json.load(open(TRADES_FILE))
    except:
        pass

# Connect REAL
api = IQ_Option(cfg.IQ_OPTION_EMAIL, cfg.IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("REAL")
time.sleep(2)

balance = api.get_balance()
log(f"START: bal={balance} trades_loaded={len(trades)}")

# Get paying assets
all_a = api.get_all_open_time()
all_pairs = {x: v for x, v in all_a['turbo'].items() if v['open']}
paying = {}
for asset in list(all_pairs.keys()):
    try:
        p = api.get_digital_payout(asset)
        if p and p >= 85:  # Only high-payout assets
            paying[asset] = p
    except:
        pass

top = sorted(paying, key=paying.get, reverse=True)  # All paying assets

# Scan
skipped_adx = 0
skipped_signal = 0
for asset in top:
    if balance < AMOUNT:
        log(f"  BALANCE TOO LOW: {balance} < {AMOUNT}")
        break

    try:
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 30:
            continue
    except:
        continue

    try:
        result = strat.analyze(api, asset, candles)
        if result is None:
            skipped_signal += 1
            continue
        if isinstance(result, str):
            direction, confidence = result, 50
        else:
            direction, confidence = result
    except Exception as e:
        log(f"  {asset} ERROR in analyze: {e}")
        continue

    if direction is None:
        if confidence == 0:
            skipped_adx += 1  # Blocked by ADX filter
        else:
            skipped_signal += 1
        continue

    # Place trade
    try:
        ok, tid = api.buy(AMOUNT, asset, direction, 1)
        if not ok:
            log(f"  {asset} {direction} FAIL: {tid}")
            continue
    except Exception as e:
        log(f"  {asset} {direction} ERROR: {e}")
        continue

    # Wait for result
    time.sleep(65)
    try:
                result = api.check_win_digital_v2(tid)
        if isinstance(result, (list, tuple)):
            win = bool(result[0])
        else:
            win = bool(result)
    except:
        win = False

    profit = AMOUNT * (paying.get(asset, 87) / 100) if win else -AMOUNT
    trade = {
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "asset": asset,
        "direction": direction,
        "amount": AMOUNT,
        "confidence": confidence,
        "profit": profit,
        "win": win
    }
    trades.append(trade)
    json.dump(trades, open(TRADES_FILE, "w"), indent=2)

    balance += profit
    w = sum(1 for t in trades if t['win'])
    log(f"  {asset} {direction.upper()} {'WIN' if win else 'LOSS'} now={w}/{len(trades)} {w/len(trades)*100:.0f}% pnl={sum(t['profit'] for t in trades):+.1f} bal={balance:.1f}")

    # Max 1 trade per cycle for REAL
    break

# Status
w = sum(1 for t in trades if t['win'])
t = len(trades)
pnl = sum(t['profit'] for t in trades)
wr = f"{w/t*100:.0f}%" if t > 0 else "0%"
log(f"CYCLE: {t}t {w}w/{t-w}l {wr} pnl={pnl:+.1f} bal={balance:.1f} adx_blocked={skipped_adx} nosig={skipped_signal}")
