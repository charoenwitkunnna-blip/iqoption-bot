#!/usr/bin/env python3
"""PRACTICE — ZETA HYBRID on 5-minute candles + 5-min expiry."""
import sys, os, time, json, importlib

AMOUNT = 5
BASE_DIR = "/root/iqoption-bot/experiments"
RESULTS_DIR = os.path.join(BASE_DIR, "results")
LOG_FILE = os.path.join(RESULTS_DIR, "zeta5_live.log")
TRADES_FILE = os.path.join(RESULTS_DIR, "zeta5_live_trades.json")

sys.path.insert(0, BASE_DIR)
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

strat = importlib.import_module("new_algos.zeta_hybrid.strategy")

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

trades = json.load(open(TRADES_FILE)) if os.path.exists(TRADES_FILE) else []

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect(); api.change_balance("PRACTICE"); time.sleep(2)

all_a = api.get_all_open_time()
all_pairs = {x: v for x, v in all_a['turbo'].items() if v['open']}
paying = {}
for asset in list(all_pairs.keys()):
    try:
        p = api.get_digital_payout(asset)
        if p and p >= 85: paying[asset] = p
    except: pass

top = sorted(paying, key=paying.get, reverse=True)

for asset in top:
    # 5-minute candles
    try:
        candles = api.get_candles(asset, 300, 40, time.time())
        if not candles or len(candles) < 25: continue
    except: continue

    try: direction, confidence = strat.analyze(api, asset, candles)
    except: continue
    if direction is None: continue

    # 5-minute expiry
    try:
        ok, tid = api.buy(AMOUNT, asset, direction, 5)
        if not ok:
            log(f"  {asset} {direction} FAIL: {tid}")
            continue
    except: continue

    time.sleep(305)
    try:         result = api.check_win_digital_v2(tid)
        if isinstance(result, (list, tuple)):
            win = bool(result[0])
        else:
            win = bool(result)
    except: win = False

    profit = AMOUNT * (paying.get(asset, 87) / 100) if win else -AMOUNT
    trade = {"time": time.strftime('%Y-%m-%d %H:%M:%S'), "asset": asset,
             "direction": direction, "amount": AMOUNT, "confidence": confidence,
             "profit": profit, "win": win}
    trades.append(trade)
    json.dump(trades, open(TRADES_FILE, "w"), indent=2)

    w = sum(1 for t in trades if t['win'])
    log(f"  {asset} {direction.upper()} {'WIN' if win else 'LOSS'} now={w}/{len(trades)} {w/len(trades)*100:.0f}% pnl={sum(t['profit'] for t in trades):+.1f}")
    break

w = sum(1 for t in trades if t['win']); t = len(trades); pnl = sum(t['profit'] for t in trades)
log(f"DONE: {t}t {w}w/{t-w}l {f'{w/t*100:.0f}%' if t>0 else '0%'} pnl={pnl:+.1f}")
