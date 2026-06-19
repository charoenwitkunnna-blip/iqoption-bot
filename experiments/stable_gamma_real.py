#!/usr/bin/env python3
"""REAL balance — gamma_breakout. Simple and reliable."""
import sys, os, time, json, importlib

AMOUNT = 30.01
BASE_DIR = "/root/iqoption-bot/experiments"
RESULTS_DIR = os.path.join(BASE_DIR, "results")
LOG_FILE = os.path.join(RESULTS_DIR, "gamma_real.log")
TRADES_FILE = os.path.join(RESULTS_DIR, "gamma_real_trades.json")

sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, '..'))
import config as cfg
from iqoptionapi.stable_api import IQ_Option

strat = importlib.import_module("new_algos.gamma_breakout.strategy")

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

trades = json.load(open(TRADES_FILE)) if os.path.exists(TRADES_FILE) else []

api = IQ_Option(cfg.IQ_OPTION_EMAIL, cfg.IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("REAL")
time.sleep(2)
balance = api.get_balance()

# Get paying assets
log(f"CYCLE: scanning... bal={balance:.1f}")
all_a = api.get_all_open_time()
all_pairs = {x: v for x, v in all_a['turbo'].items() if v['open']}
paying = {}
for asset in list(all_pairs.keys())[:80]:  # Enough for good coverage
    try:
        p = api.get_digital_payout(asset)
        if p and p >= 85:
            paying[asset] = p
    except: pass

top = sorted(paying, key=paying.get, reverse=True)
recent_assets = []

for asset in top:
    if asset in recent_assets: continue
    try:
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 30: continue
    except: continue

    try:
        direction, confidence = strat.analyze(api, asset, candles)
    except: continue

    if direction is None: continue

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

    payout_pct = paying.get(asset, 87)
    profit = AMOUNT * (payout_pct / 100) if win else -AMOUNT
    trade = {
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "asset": asset, "direction": direction,
        "amount": AMOUNT, "confidence": confidence,
        "profit": profit, "win": win, "payout": payout_pct
    }
    trades.append(trade)
    json.dump(trades, open(TRADES_FILE, "w"), indent=2)

    recent_assets.append(asset)
    if len(recent_assets) > 3:
        recent_assets.pop(0)

    balance += profit
    w = sum(1 for t in trades if t['win'])
    log(f"  {asset} {direction.upper()} {'WIN' if win else 'LOSS'} now={w}/{len(trades)} {w/len(trades)*100:.0f}% pnl={sum(t['profit'] for t in trades):+.1f} bal={balance:.1f}")
    break

w = sum(1 for t in trades if t['win'])
t = len(trades)
pnl = sum(t['profit'] for t in trades)
wr = f"{w/t*100:.0f}%" if t > 0 else "0%"
log(f"DONE: {t}t {w}w/{t-w}l {wr} pnl={pnl:+.1f} bal={balance:.1f}")
