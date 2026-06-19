#!/usr/bin/env python3
"""PRACTICE — RHO CALL TEST. Same logic as rho_bounce but CALL only."""
import sys, os, time, json, importlib
import random

AMOUNT = 5
EXPIRY = 1
BASE_DIR = "/root/iqoption-bot/experiments"
RESULTS = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS, exist_ok=True)

sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, '..'))
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

strat = importlib.import_module("new_algos.rho_call_test.strategy")

log_file = os.path.join(RESULTS, "rho_call_test.log")
trades_file = os.path.join(RESULTS, "rho_call_test_trades.json")

def log(msg):
    with open(log_file, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def load_trades():
    if os.path.exists(trades_file):
        try: return json.load(open(trades_file))
        except: pass
    return []

def save_trades(trades):
    json.dump(trades, open(trades_file, "w"), indent=2)

trades = load_trades()
TARGET = 20

while len(trades) < TARGET:
    api = None
    try:
        api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
        api.connect()
        api.change_balance("PRACTICE")
        time.sleep(2)

        bal = api.get_balance()
        if bal < AMOUNT:
            log(f"BALANCE LOW: {bal}")
            try: api._close_connect = lambda: None; api._close_connect()
            except: pass
            time.sleep(60)
            continue

        all_open = api.get_all_open_time()
        open_assets = {k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}
        paying = {}
        for asset in random.sample(list(open_assets.keys()), min(25, len(open_assets))):
            try:
                p = api.get_digital_payout(asset)
                if p and p >= 85: paying[asset] = p
            except: pass

        if not paying:
            log("NO ASSETS")
            try: api._close_connect = lambda: None; api._close_connect()
            except: pass
            time.sleep(30)
            continue

        top = sorted(paying, key=paying.get, reverse=True)
        traded = False

        for asset in top:
            try:
                candles = api.get_candles(asset, 60, 50, time.time())
                if not candles or len(candles) < 30: continue
            except: continue

            try:
                direction, confidence = strat.analyze(api, asset, candles)
            except: continue
            if direction is None: continue

            ok, tid = api.buy(AMOUNT, asset, direction, EXPIRY)
            if not ok:
                log(f"  {asset} {direction} FAIL: {tid}")
                continue

            log(f"  {asset} {direction} conf={confidence} TID={tid}")
            time.sleep(68)

            try:
                result = api.check_win_v4(tid)
                win = result[0] == 'win'
            except:
                win = False

            profit = AMOUNT * (paying.get(asset, 87) / 100) if win else -AMOUNT
            trade = {"time": time.strftime('%Y-%m-%d %H:%M:%S'),
                     "asset": asset, "direction": direction,
                     "amount": AMOUNT, "confidence": confidence,
                     "profit": profit, "win": win}
            trades.append(trade)
            save_trades(trades)

            w = sum(1 for t in trades if t['win'])
            num = len(trades)
            wr = w / num * 100 if num > 0 else 0
            pnl_total = sum(t['profit'] for t in trades)
            log(f"  {asset} {direction.upper()} {'WIN' if win else 'LOSS'} now={w}/{num} {wr:.0f}% pnl={pnl_total:+.1f}")
            traded = True
            break

        if not traded:
            log("NO SIGNAL")

        try: api._close_connect = lambda: None; api._close_connect()
        except: pass

    except Exception as e:
        log(f"ERROR: {e}")
        try:
            if api: api._close_connect = lambda: None; api._close_connect()
        except: pass

    time.sleep(15)

# Done
w = sum(1 for t in trades if t['win'])
l = len(trades) - w
wr = w / len(trades) * 100
pnl = sum(t['profit'] for t in trades)
log(f"DONE: {len(trades)}t {w}W/{l}L = {wr:.0f}% pnl={pnl:+.1f}")
