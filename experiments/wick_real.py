#!/usr/bin/env python3
"""REAL balance — WICK HAMMER strategy."""
import sys, os, time, json, importlib

AMOUNT = 30
STOP_LOSS = -90
BASE_DIR = "/root/iqoption-bot/experiments"
RESULTS = os.path.join(BASE_DIR, "results")
LOG_FILE = os.path.join(RESULTS, "wick_hammer.log")
TRADES_FILE = os.path.join(RESULTS, "wick_hammer_trades.json")

sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, '..'))
import config as cfg
from iqoptionapi.stable_api import IQ_Option

strat = importlib.import_module("new_algos.wick_hammer.strategy")

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def load_trades():
    if os.path.exists(TRADES_FILE):
        try: return json.load(open(TRADES_FILE))
        except: pass
    return []

def save_trades(trades):
    json.dump(trades, open(TRADES_FILE, "w"), indent=2)

trades = load_trades()
first = True

while True:
    api = None
    try:
        api = IQ_Option(cfg.IQ_OPTION_EMAIL, cfg.IQ_OPTION_PASSWORD)
        api.connect()
        api.change_balance("REAL")
        time.sleep(2)

        bal = api.get_balance()
        total_pnl = sum(t['profit'] for t in trades)
        if total_pnl <= STOP_LOSS:
            log(f"STOP LOSS: {total_pnl} bal={bal}")
            try: api._close_connect = lambda: None; api._close_connect()
            except: pass
            time.sleep(60)
            continue

        if bal < AMOUNT:
            log(f"BALANCE TOO LOW: {bal}")
            try: api._close_connect = lambda: None; api._close_connect()
            except: pass
            time.sleep(60)
            continue

        all_open = api.get_all_open_time()
        open_assets = {k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}
        paying = {}
        for asset in list(open_assets.keys())[:60]:
            try:
                p = api.get_digital_payout(asset)
                if p and p >= 85: paying[asset] = p
            except: pass

        if not paying:
            if first:
                log(f"NO ASSETS — waiting")
                first = False
            try: api._close_connect = lambda: None; api._close_connect()
            except: pass
            time.sleep(30)
            continue

        first = False
        top = sorted(paying, key=paying.get, reverse=True)
        traded = False

        for asset in top:
            try:
                candles = api.get_candles(asset, 60, 50, time.time())
                if not candles or len(candles) < 20: continue
            except: continue

            try:
                direction, confidence = strat.analyze(api, asset, candles)
            except: continue
            if direction is None: continue

            ok, tid = api.buy(AMOUNT, asset, direction, 1)
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
            if not first:
                log("NO SIGNAL")

        try: api._close_connect = lambda: None; api._close_connect()
        except: pass

    except Exception as e:
        log(f"ERROR: {e}")
        try:
            if api: api._close_connect = lambda: None; api._close_connect()
        except: pass

    time.sleep(15)
